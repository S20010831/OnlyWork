"""Small, injectable storage primitives shared by all persistent services."""

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator

logger = logging.getLogger(__name__)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


@contextmanager
def preserve_file(path: Path) -> Iterator[None]:
    """Restore a cache if a later step in the same operation fails."""
    try:
        previous = path.read_bytes()
    except FileNotFoundError:
        previous = None
    backup: Path | None = None
    keep_backup = False
    try:
        if previous is not None:
            with NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=path.name + ".",
                suffix=".rollback",
                delete=False,
            ) as stream:
                backup = Path(stream.name)
                stream.write(previous)
                stream.flush()
                os.fsync(stream.fileno())
        try:
            yield
        except BaseException as original_error:
            try:
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    try:
                        current = path.read_bytes()
                    except FileNotFoundError:
                        current = None
                    if current != previous:
                        backup.replace(path)
            except OSError as restore_error:
                keep_backup = True
                recovery = f"；原文件备份：{backup}" if backup is not None else ""
                raise OSError(
                    f"保存失败（{original_error}），且无法恢复 {path}：{restore_error}{recovery}"
                ) from restore_error
            raise
    finally:
        if backup is not None and not keep_backup:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                logger.warning("could not remove cache backup: %s", backup, exc_info=True)


def write_json(path: Path, value: Any) -> None:
    """Replace a file atomically so interrupted writes cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

"""Action handlers are registered explicitly and receive a small host interface."""

import os
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Protocol
from urllib.parse import urlsplit

from .models import ExtensionAction


class ActionError(ValueError):
    pass


class ActionContext(Protocol):
    base_directory: Path

    def show_info(self, text: str) -> None: ...
    def open_url(self, url: str) -> None: ...
    def play_audio(self, path: Path) -> None: ...


class ActionHandler(Protocol):
    def validate(self, value: str) -> None: ...
    def prepare(self, value: str, source_directory: Path, data_directory: Path) -> str: ...
    def execute(self, value: str, context: ActionContext) -> None: ...


@dataclass
class CallbackAction:
    callback: Callable[[str, ActionContext], None]
    validator: Callable[[str], None] | None = None

    def validate(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ActionError("扩展内容不能为空")
        if self.validator:
            self.validator(value)

    def prepare(self, value: str, source_directory: Path, data_directory: Path) -> str:
        return value

    def execute(self, value: str, context: ActionContext) -> None:
        self.callback(value, context)


def validate_url(value: str) -> None:
    try:
        url = urlsplit(value)
        if url.scheme.lower() not in {"http", "https"} or not url.hostname:
            raise ValueError
        _ = url.port
    except ValueError as error:
        raise ActionError("链接必须是有效的 http:// 或 https:// 地址") from error


class AudioAction:
    def validate(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ActionError("音频路径不能为空")

    def prepare(self, value: str, source_directory: Path, data_directory: Path) -> str:
        source = Path(value).expanduser()
        if not source.is_absolute():
            source = source_directory / source
        if not source.is_file():
            raise ActionError(f"音频文件不存在：{source}")
        digest = sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        relative = Path("assets") / (digest.hexdigest() + source.suffix.lower())
        destination = data_directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = None
            try:
                with NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    with source.open("rb") as original:
                        shutil.copyfileobj(original, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(destination)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return relative.as_posix()

    def execute(self, value: str, context: ActionContext) -> None:
        path = Path(value)
        if not path.is_absolute():
            path = context.base_directory / path
        if not path.is_file():
            raise ActionError(f"音频文件不存在：{path}")
        context.play_audio(path.resolve())


class ActionRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, name: str, handler: ActionHandler) -> None:
        if not name or name in self._handlers:
            raise ValueError(f"扩展动作已注册或名称为空：{name}")
        self._handlers[name] = handler

    def get(self, name: str) -> ActionHandler:
        try:
            return self._handlers[name]
        except KeyError as error:
            raise ActionError(f"不支持的扩展动作：{name}") from error

    def validate(self, action: ExtensionAction | None) -> None:
        if action:
            self.get(action.type).validate(action.value)

    def prepare(self, action: ExtensionAction, source: Path, data: Path) -> ExtensionAction:
        handler = self.get(action.type)
        handler.validate(action.value)
        return ExtensionAction(action.type, handler.prepare(action.value, source, data))

    def run(self, action: ExtensionAction, context: ActionContext) -> None:
        self.validate(action)
        self.get(action.type).execute(action.value, context)


def default_actions() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register("info", CallbackAction(lambda value, context: context.show_info(value)))
    registry.register(
        "url", CallbackAction(lambda value, context: context.open_url(value), validate_url)
    )
    registry.register("audio", AudioAction())
    return registry

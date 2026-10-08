from pathlib import Path

import pytest

from app.storage import preserve_file, read_json, write_json


def test_successful_operation_keeps_new_file_and_removes_backup(tmp_path):
    path = tmp_path / "library.json"
    path.write_bytes(b"original cache")

    with preserve_file(path):
        write_json(path, {"bank": "new"})

    assert read_json(path) == {"bank": "new"}
    assert set(tmp_path.iterdir()) == {path}


def test_backup_cleanup_failure_keeps_successful_save(tmp_path, monkeypatch, caplog):
    path = tmp_path / "library.json"
    original = b"original cache"
    path.write_bytes(original)
    unlink = Path.unlink

    def fail_backup_cleanup(self, *args, **kwargs):
        if self.suffix == ".rollback":
            raise PermissionError("backup locked")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_backup_cleanup)

    with preserve_file(path):
        write_json(path, {"bank": "new"})

    backups = list(tmp_path.glob("*.rollback"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert read_json(path) == {"bank": "new"}
    assert any(
        record.levelname == "WARNING" and str(backups[0]) in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize("original", [b"", b"original bytes\r\n\xff"])
def test_failed_later_step_restores_exact_original_bytes(tmp_path, original):
    path = tmp_path / "library.json"
    path.write_bytes(original)
    failure = ValueError("review commit failed")

    with pytest.raises(ValueError) as captured:
        with preserve_file(path):
            write_json(path, {"bank": "new"})
            raise failure

    assert captured.value is failure
    assert path.read_bytes() == original
    assert set(tmp_path.iterdir()) == {path}


def test_failed_later_step_removes_new_file_when_original_was_absent(tmp_path):
    path = tmp_path / "nested" / "library.json"

    with pytest.raises(ValueError, match="review commit failed"):
        with preserve_file(path):
            write_json(path, {"bank": "new"})
            raise ValueError("review commit failed")

    assert not path.exists()
    assert not list(path.parent.iterdir())


def test_failed_atomic_write_preserves_cache_without_another_replace(tmp_path, monkeypatch):
    path = tmp_path / "library.json"
    original = b"original cache"
    path.write_bytes(original)
    replacements = []

    def fail_replace(self, target):
        replacements.append((self, target))
        raise PermissionError("cache locked")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(PermissionError, match="cache locked"):
        with preserve_file(path):
            write_json(path, {"bank": "new"})

    assert path.read_bytes() == original
    assert len(replacements) == 1
    assert set(tmp_path.iterdir()) == {path}


def test_failed_rollback_preserves_recovery_copy_and_reports_both_errors(tmp_path, monkeypatch):
    path = tmp_path / "library.json"
    original = b"original cache"
    path.write_bytes(original)

    with pytest.raises(OSError) as captured:
        with preserve_file(path):
            write_json(path, {"bank": "new"})

            def fail_replace(self, target):
                raise PermissionError("rollback denied")

            monkeypatch.setattr(Path, "replace", fail_replace)
            raise ValueError("review commit failed")

    backups = list(tmp_path.glob("*.rollback"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert read_json(path) == {"bank": "new"}
    assert "review commit failed" in str(captured.value)
    assert "rollback denied" in str(captured.value)
    assert str(backups[0]) in str(captured.value)

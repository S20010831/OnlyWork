import json
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtGui import QColor

from app.config import SettingsManager
from app.extensions import ActionError, CallbackAction, default_actions
from app.library import LibraryStore
from app.models import ExtensionAction, QuestionFormatError
from app.questions import SAMPLE_QUESTIONS, question_to_dict
from app.storage import read_json, write_json


def test_failed_atomic_replace_preserves_old_file(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "settings.json"
    write_json(path, {"saved": 1})

    def fail_replace(self, target):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError):
        write_json(path, {"saved": 2})
    assert read_json(path) == {"saved": 1}
    assert not list(path.parent.glob("*.tmp"))


def test_settings_roundtrip_preserves_behavior_during_theme_changes(tmp_path):
    path = tmp_path / "settings.json"
    settings = SettingsManager(path)
    settings.set_behavior(feedback_delay_ms=900, hide_delay_ms=200)
    settings.set_color("background", QColor("#FF112233"))
    restored = SettingsManager(path)
    assert restored.behavior.feedback_delay_ms == 900
    assert restored.colors.background == "#FF112233"
    restored.reset_colors()
    assert SettingsManager(path).behavior.hide_delay_ms == 200


def test_partial_corrupt_settings_keep_valid_fields(tmp_path):
    path = tmp_path / "settings.json"
    write_json(
        path,
        {
            "theme": {"text": "#FF112233", "background": "bad", "future": 1},
            "behavior": {"feedback_delay_ms": 900, "hide_delay_ms": "bad"},
        },
    )
    settings = SettingsManager(path)
    assert settings.colors.text == "#FF112233"
    assert settings.behavior.feedback_delay_ms == 900
    assert settings.behavior.hide_delay_ms == 0
    write_json(path, [])
    assert SettingsManager(path).behavior.feedback_delay_ms == 650


def test_imported_bank_survives_deleting_source_and_reordering(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps([question_to_dict(q) for q in reversed(SAMPLE_QUESTIONS)]), encoding="utf-8"
    )
    store = LibraryStore(tmp_path / "saved" / "library.json")
    library = store.import_file(source)
    source.unlink()
    assert store.load() == library
    assert library.questions[0].id == SAMPLE_QUESTIONS[1].id


def test_failed_import_keeps_saved_bank(tmp_path):
    store = LibraryStore(tmp_path / "saved" / "library.json")
    source = tmp_path / "source.json"
    source.write_text(json.dumps([question_to_dict(q) for q in SAMPLE_QUESTIONS]), encoding="utf-8")
    original = store.import_file(source)
    source.write_text("invalid json", encoding="utf-8")
    with pytest.raises(QuestionFormatError):
        store.import_file(source)
    assert store.load() == original


def test_audio_asset_is_cached_and_dispatched_after_original_is_deleted(tmp_path, action_context):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    original = source_dir / "sound.wav"
    with wave.open(str(original), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 800)
    question = replace(SAMPLE_QUESTIONS[0], extension=ExtensionAction("audio", "sound.wav"))
    source = source_dir / "bank.json"
    source.write_text(json.dumps([question_to_dict(question)]), encoding="utf-8")
    store = LibraryStore(tmp_path / "data" / "library.json")
    loaded = store.import_file(source).questions[0]
    original.unlink()
    source.unlink()
    action_context.base_directory = store.path.parent
    store.actions.run(loaded.extension, action_context)
    assert action_context.audio[0].is_file()
    assert loaded.id == question.id
    assert store.load().questions[0] == loaded


def test_custom_action_roundtrip(tmp_path, action_context):
    actions = default_actions()
    actions.register(
        "lookup", CallbackAction(lambda value, context: context.show_info("lookup:" + value))
    )
    question = replace(SAMPLE_QUESTIONS[0], extension=ExtensionAction("lookup", "word"))
    path = tmp_path / "bank.json"
    path.write_text(json.dumps([question_to_dict(question)]), encoding="utf-8")
    store = LibraryStore(tmp_path / "data" / "library.json", actions=actions)
    loaded = store.import_file(path).questions[0]
    actions.run(loaded.extension, action_context)
    assert action_context.info == ["lookup:word"]


@pytest.mark.parametrize(
    "value", ["javascript:alert(1)", "file:///c:/x", "https://", "https://example.com:bad"]
)
def test_url_action_rejects_invalid_links(value, action_context):
    with pytest.raises(ActionError):
        default_actions().run(ExtensionAction("url", value), action_context)


def test_builtin_info_url_and_missing_audio(action_context):
    actions = default_actions()
    actions.run(ExtensionAction("info", "plain text"), action_context)
    actions.run(ExtensionAction("url", "https://example.com/path"), action_context)
    assert action_context.info == ["plain text"]
    assert action_context.urls == ["https://example.com/path"]
    with pytest.raises(ActionError):
        actions.run(ExtensionAction("audio", "absent.wav"), action_context)

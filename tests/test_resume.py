"""Exercise restart progress through temporary, service-free application instances."""

import json
from contextlib import contextmanager
from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from app.questions import SAMPLE_QUESTIONS, question_to_dict
from main import App


def write_bank(path, identifiers=("1", "2", "3")):
    questions = [
        replace(SAMPLE_QUESTIONS[0], id=identifier, prompt=f"Question {identifier}")
        for identifier in identifiers
    ]
    path.write_text(json.dumps([question_to_dict(q) for q in questions]), encoding="utf-8")
    return path


def answer_counts(application):
    return {
        identifier: (state.attempts, state.correct, state.incorrect)
        for identifier, state in application.scheduler.states.items()
    }


@contextmanager
def restarted(application, qapp):
    application.shutdown()
    instance = App(
        qapp,
        data_dir=application.library_store.path.parent,
        services=application.services,
        start_services=False,
    )
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.settings.deleteLater()
        instance.overlay.deleteLater()
        instance.tray.deleteLater()
        instance.tray_menu.deleteLater()
        qapp.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("wrong_answer", [False, True], ids=["unfinished", "incorrect"])
def test_restart_restores_current_question_and_keeps_answer_counts(
    application, qapp, tmp_path, wrong_answer
):
    source = write_bank(tmp_path / "questions.json")
    application.import_library(str(source))
    application.controller.navigate_question("next")
    assert application.session.question.id == "2"
    if wrong_answer:
        application.controller.select_option("B")
        assert application.session.feedback == "incorrect"
    before = answer_counts(application)
    source.unlink()

    with restarted(application, qapp) as restored:
        assert restored.session.question.id == "2"
        assert restored.session.selected == frozenset()
        assert restored.session.feedback is None
        assert answer_counts(restored) == before


def test_restart_after_correct_answer_continues_without_recording_it_twice(
    application, qapp, tmp_path
):
    class RecordingStrategy:
        def __init__(self):
            self.identifiers = []

        def score(self, state, current):
            self.identifiers.append(state.question_id)
            return 1.0

    application.import_library(str(write_bank(tmp_path / "questions.json")))
    application.controller.navigate_question("next")
    application.controller.select_option("A")
    assert application.session.question.id == "2"
    assert application.session.feedback == "correct"
    assert application.controller.next_question_timer.interval() == 650
    assert application.controller.next_question_timer.isActive()
    before = answer_counts(application)
    strategy = RecordingStrategy()
    application.services.review_strategy = strategy

    with restarted(application, qapp) as restored:
        assert restored.session.question.id in {"1", "3"}
        assert set(strategy.identifiers) == {"1", "3"}
        assert restored.session.feedback is None
        assert not restored.session.selected
        assert answer_counts(restored) == before
        next_identifier = restored.session.question.id
        calls_after_recommendation = list(strategy.identifiers)
        with restarted(restored, qapp) as restored_again:
            assert restored_again.session.question.id == next_identifier
            assert answer_counts(restored_again) == before
            assert strategy.identifiers == calls_after_recommendation


def test_each_bank_restores_its_own_current_question(application, qapp, tmp_path):
    english = write_bank(tmp_path / "english.json")
    math = write_bank(tmp_path / "math.json")
    application.import_library(str(english))
    english_bank = application.library.id
    application.controller.navigate_question("next")
    application.controller.select_option("B")
    application.import_library(str(math))
    assert application.library.id != english_bank
    application.controller.navigate_question("next")
    application.controller.navigate_question("next")
    assert application.session.question.id == "3"
    application.import_library(str(english))
    assert application.session.question.id == "2"
    assert application.scheduler.states["2"].incorrect == 1

    with restarted(application, qapp) as restored:
        assert restored.session.question.id == "2"
        restored.import_library(str(math))
        assert restored.session.question.id == "3"
        assert restored.scheduler.states["2"].attempts == 0

    with restarted(application, qapp) as restored:
        assert restored.session.question.id == "3"


def test_reimport_reordered_questions_restores_by_id(application, qapp, tmp_path):
    source = write_bank(tmp_path / "questions.json")
    application.import_library(str(source))
    bank_identifier = application.library.id
    application.controller.navigate_question("next")
    assert application.session.index == 1
    write_bank(source, ("3", "1", "2"))
    application.import_library(str(source))
    assert application.library.id == bank_identifier
    assert application.session.question.id == "2"
    assert application.session.index == 2

    with restarted(application, qapp) as restored:
        assert restored.session.question.id == "2"
        assert restored.session.index == 2


def test_reimport_deleted_current_question_selects_and_saves_a_valid_question(
    application, qapp, tmp_path
):
    source = write_bank(tmp_path / "questions.json")
    application.import_library(str(source))
    application.controller.navigate_question("next")
    assert application.session.question.id == "2"
    write_bank(source, ("1", "3"))
    application.import_library(str(source))
    assert application.session.question.id in {"1", "3"}
    replacement = application.session.question.id

    with restarted(application, qapp) as restored:
        assert restored.session.question.id == replacement


@pytest.mark.parametrize("transition", ["previous", "next", "recommended"])
def test_failed_transition_keeps_current_question_and_restart_position(
    application, qapp, tmp_path, monkeypatch, transition
):
    application.import_library(str(write_bank(tmp_path / "questions.json")))
    application.controller.navigate_question("next")
    assert application.session.question.id == "2"
    previous_file = application.scheduler.path.read_bytes()
    previous_counts = answer_counts(application)
    original_save = application.scheduler.save

    def fail_save():
        raise PermissionError("test progress file locked")

    monkeypatch.setattr(application.scheduler, "save", fail_save)
    if transition == "recommended":
        application.controller.next_question()
    else:
        application.controller.navigate_question(transition)
    assert application.session.question.id == "2"
    assert answer_counts(application) == previous_counts
    assert application.scheduler.path.read_bytes() == previous_file
    assert application.test_warnings
    monkeypatch.setattr(application.scheduler, "save", original_save)

    with restarted(application, qapp) as restored:
        assert restored.session.question.id == "2"
        assert answer_counts(restored) == previous_counts


@pytest.mark.parametrize("import_kind", ["same-bank", "different-bank", "first-import"])
@pytest.mark.parametrize("failed_file", ["cache", "progress"])
def test_failed_import_keeps_original_bank_and_resume_position(
    application, qapp, tmp_path, monkeypatch, import_kind, failed_file
):
    source = write_bank(tmp_path / "original.json")
    if import_kind != "first-import":
        application.import_library(str(source))
    application.controller.navigate_question("next")
    if import_kind != "first-import":
        application.controller.select_option("B")
    old_library = application.library
    old_question = application.session.question
    old_position = application.scheduler.position
    old_counts = answer_counts(application)
    progress_file = application.scheduler.path.read_bytes()
    cache_path = application.library_store.path
    cache_file = cache_path.read_bytes() if cache_path.exists() else None
    if import_kind == "same-bank":
        # Reimport the same source after deleting the current question.
        write_bank(source, ("1", "3", "4"))
    else:
        source = write_bank(tmp_path / "replacement.json", ("1", "3", "4"))

    def fail(*args):
        raise PermissionError(f"test {failed_file} file locked")

    with monkeypatch.context() as patch:
        if failed_file == "cache":
            patch.setattr(application.library_store, "save", fail)
        else:
            patch.setattr("app.scheduler.write_json", fail)
        application.import_library(str(source))

    assert application.library == old_library
    assert application.session.question == old_question
    assert application.scheduler.bank_id == old_library.id
    assert application.scheduler.position == old_position
    assert answer_counts(application) == old_counts
    assert application.scheduler.path.read_bytes() == progress_file
    if cache_file is None:
        assert not cache_path.exists()
    else:
        assert cache_path.read_bytes() == cache_file
    assert not list(cache_path.parent.glob("*.rollback"))
    assert f"test {failed_file} file locked" in application.test_warnings[-1]

    with restarted(application, qapp) as restored:
        assert restored.library == old_library
        assert restored.session.question == old_question
        assert answer_counts(restored) == old_counts
        # A failed commit must not leave saving disabled for the next import.
        restored.import_library(str(source))
        assert restored.library.id == restored.scheduler.bank_id
        assert restored.session.questions == restored.library.questions

        with restarted(restored, qapp) as restored_again:
            assert restored_again.library == restored.library
            assert restored_again.session.question == restored.session.question

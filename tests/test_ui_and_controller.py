import json
import math
from dataclasses import replace

import pytest
from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from app.extensions import CallbackAction
from app.geometry import overlay_top_left
from app.models import ExtensionAction, Option, QuizQuestion
from app.questions import SAMPLE_QUESTIONS, question_to_dict
from main import App


def click_option(application, index):
    widget = application.overlay.widget
    point = widget.option_layouts()[index].rect.center()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point)


def test_single_ui_clicks_record_wrong_and_right_once(application):
    click_option(application, 1)
    identifier = application.session.question.id
    assert application.session.feedback == "incorrect"
    assert application.scheduler.states[identifier].incorrect == 1
    click_option(application, 0)
    assert application.session.selected == {"A"}
    assert application.session.feedback == "correct"
    application.controller.confirm_answer()
    application.controller.confirm_answer()
    state = application.scheduler.states[identifier]
    assert (state.attempts, state.correct, state.incorrect) == (2, 1, 1)
    assert application.controller.next_question_timer.isActive()


def test_ui_multiple_confirmation_and_navigation_cancel_timer(application):
    application.controller.navigate_question("next")
    identifier = application.session.question.id
    for index in (0, 1, 3):
        click_option(application, index)
    assert application.session.feedback is None
    widget = application.overlay.widget
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=widget.corner_centers()[1])
    assert application.session.feedback == "correct"
    assert application.scheduler.states[identifier].attempts == 1
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=widget.corner_centers()[2])
    assert not application.controller.next_question_timer.isActive()
    assert application.session.index == 0 and not application.session.selected


def test_correct_timer_moves_to_another_question(application):
    previous = application.session.question.id
    application.controller.next_question_timer.setInterval(10)
    click_option(application, 0)
    QTest.qWait(40)
    assert application.session.question.id != previous
    assert not application.session.selected and application.session.feedback is None


def test_import_dialog_signal_replaces_bank_and_restart_restores_it(
    application, qapp, tmp_path, monkeypatch
):
    source = tmp_path / "custom.json"
    question = replace(SAMPLE_QUESTIONS[0], id="imported-question", prompt="Imported")
    source.write_text(json.dumps([question_to_dict(question)]), encoding="utf-8")
    # Start a pending transition to ensure import cancels it.
    click_option(application, 0)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    application.settings.import_questions()
    assert application.session.question.prompt == "Imported"
    assert not application.controller.next_question_timer.isActive()
    assert "custom.json" in application.settings.path_label.text()
    source.unlink()
    restored = App(qapp, data_dir=application.library_store.path.parent, start_services=False)
    try:
        assert restored.session.question.id == "imported-question"
        assert len(restored.session.questions) == 1
    finally:
        restored.shutdown()
        restored.settings.deleteLater()
        restored.overlay.deleteLater()
        restored.tray.deleteLater()
        restored.tray_menu.deleteLater()


def test_failed_import_reports_error_and_keeps_active_bank(application, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("bad", encoding="utf-8")
    before = application.session.questions
    application.import_library(str(path))
    assert application.session.questions == before
    assert application.test_warnings and "导入失败" in application.test_warnings[0]


def test_preferences_apply_immediately_and_persist(application):
    application.settings.behavior_inputs["feedback_delay_ms"].setValue(900)
    assert application.controller.next_question_timer.interval() == 900
    saved = json.loads(application.preferences.path.read_text(encoding="utf-8"))
    assert saved["behavior"]["feedback_delay_ms"] == 900


def test_separate_hover_selection_colors_and_center_background(application):
    widget = application.overlay.widget
    for name, value in (
        ("hover_background", "#FF123456"),
        ("selected_background", "#FF654321"),
        ("background", "#FF112233"),
    ):
        application.preferences.set_color(name, QColor(value))
    application.apply_settings()
    widget.highlighted = 1
    assert widget.option_color(1) == "hover_background"
    click_option(application, 1)
    assert widget.option_color(1) == "incorrect_background"
    application.session.cancel_submission()
    assert widget.option_color(1) == "selected_background"
    image = widget.grab().toImage()
    assert image.pixelColor(90, 100).name() == "#112233"


@pytest.mark.parametrize("count", [3, 4, 5, 6])
def test_dynamic_sector_hit_tests_and_rendering(application, count):
    options = tuple(Option(chr(65 + i), "选项内容") for i in range(count))
    application.controller.load_questions(
        (QuizQuestion("Question", "subtitle", options, frozenset({"A"})),)
    )
    widget = application.overlay.widget
    center = widget.rect().center()
    for index in range(count):
        angle = math.radians(widget.option_angle(index))
        point = QPoint(
            round(center.x() + 84 * math.cos(angle)), round(center.y() + 84 * math.sin(angle))
        )
        assert widget.option_at(point) == index
        label_rect = widget.option_layouts()[index].rect
        assert not label_rect.intersects(widget.card_rect())
        assert label_rect.width() > 0 and label_rect.height() > 0
        for corner in (
            label_rect.topLeft(),
            label_rect.topRight(),
            label_rect.bottomLeft(),
            label_rect.bottomRight(),
        ):
            assert (
                math.hypot(corner.x() - center.x(), corner.y() - center.y())
                <= widget.metrics.outer_radius
            )
            assert widget.option_at(corner) == index
    assert widget.option_at(center) is None
    assert widget.option_at(QPoint(0, 0)) is None
    assert not widget.grab().isNull()


def test_missing_extension_has_no_click_target_and_custom_handler_runs(application, action_context):
    widget = application.overlay.widget
    assert widget.corner_at(widget.corner_centers()[0]) is None
    application.services.actions.register(
        "lookup", CallbackAction(lambda value, context: context.show_info(value))
    )
    question = replace(SAMPLE_QUESTIONS[0], extension=ExtensionAction("lookup", "result"))
    application.controller.action_context = action_context
    application.controller.load_questions((question,))
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=widget.corner_centers()[0])
    assert action_context.info == ["result"]


def test_plain_info_dialog_is_reusable(application):
    context = application.action_context
    context.show_info("<b>plain explanation</b>")
    assert context._info_text.toPlainText() == "<b>plain explanation</b>"
    first = context._info_dialog
    context.show_info("updated")
    assert context._info_dialog is first
    assert context._info_text.toPlainText() == "updated"


def test_storage_failure_allows_same_answer_to_be_retried(application, monkeypatch):
    original = application.scheduler.save

    def fail():
        raise PermissionError("locked")

    monkeypatch.setattr(application.scheduler, "save", fail)
    click_option(application, 0)
    assert application.session.feedback is None
    assert not application.controller.next_question_timer.isActive()
    assert application.test_warnings
    monkeypatch.setattr(application.scheduler, "save", original)
    application.controller.confirm_answer()
    assert application.session.feedback == "correct"
    assert application.scheduler.states[application.session.question.id].attempts == 1


def test_cursor_reentry_cancels_fade_and_hidden_overlay_stops_timers(application, monkeypatch):
    overlay = application.overlay
    overlay.show()
    overlay._armed = True
    overlay._cursor_entered = True
    overlay._watch.start()
    from app.overlay import QCursor

    outside = overlay.mapToGlobal(QPoint(0, 0))
    inside = overlay.mapToGlobal(overlay.rect().center())
    monkeypatch.setattr(QCursor, "pos", lambda: outside)
    overlay.check_cursor()
    assert overlay._fade.state() == QAbstractAnimation.State.Running
    monkeypatch.setattr(QCursor, "pos", lambda: inside)
    overlay.check_cursor()
    assert overlay._fade.state() == QAbstractAnimation.State.Stopped
    assert overlay.windowOpacity() == 1
    overlay.hide()
    assert not overlay._watch.isActive() and not overlay._arm_timer.isActive()


def test_position_clamp_on_negative_coordinate_monitor():
    screen = QRect(-1920, 0, 1920, 1080)
    for cursor in (QPoint(-1920, 0), QPoint(-1, 1079), QPoint(-900, 400)):
        point = overlay_top_left(cursor, screen, 240)
        assert screen.contains(QRect(point, QPoint(point.x() + 239, point.y() + 239)))


def test_import_cache_write_failure_keeps_active_and_saved_bank(application, tmp_path, monkeypatch):
    path = tmp_path / "bank.json"
    original = application.session.questions
    # Establish an existing cache, then reject its replacement.
    application.library_store.save(application.library)
    question = replace(SAMPLE_QUESTIONS[0], id="new-bank-question", prompt="New bank")
    path.write_text(json.dumps([question_to_dict(question)]), encoding="utf-8")

    def fail(library):
        raise PermissionError("locked cache")

    monkeypatch.setattr(application.library_store, "save", fail)
    application.import_library(str(path))
    assert application.session.questions == original
    assert application.library_store.load().questions == original
    assert "locked cache" in application.test_warnings[-1]

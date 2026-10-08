from dataclasses import replace

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.models import Option
from app.option_layout import wrap_option_text
from app.questions import SAMPLE_QUESTIONS


def load_options(application, texts):
    question = replace(
        SAMPLE_QUESTIONS[0],
        options=tuple(Option(chr(65 + i), text) for i, text in enumerate(texts)),
    )
    application.controller.load_questions((question,))
    application.overlay.show()
    return application.overlay.widget


def test_side_options_use_multiple_lines_without_losing_short_meanings(application):
    widget = load_options(application, ["记住；回忆", "放弃；遗弃", "烧；烧毁", "帮助；支援"])
    for index in (1, 3):
        layout = widget.option_layouts()[index]
        assert len(layout.lines) >= 2
        assert not layout.clipped
        assert "".join(layout.lines) == widget.question.options[index].text
        QTest.mouseMove(widget, layout.rect.center())
        assert widget._tooltip.isHidden()


def test_punctuation_wraps_and_only_the_overflowing_last_line_is_elided(qapp):
    font = qapp.font()
    metrics = QFontMetrics(font)
    rect = QRect(0, 0, metrics.horizontalAdvance("放弃；") + 1, metrics.lineSpacing() * 3)
    complete = wrap_option_text("放弃；抛弃；遗弃", font, rect)
    assert complete.lines == ("放弃；", "抛弃；", "遗弃")
    assert not complete.clipped
    overflow = wrap_option_text("放弃；抛弃；遗弃；离开；停止", font, rect)
    assert overflow.clipped
    assert all("…" not in line for line in overflow.lines[:-1])
    assert overflow.lines[-1].endswith("…")


def test_explicit_newlines_english_words_and_emoji_remain_readable(qapp):
    font = qapp.font()
    metrics = QFontMetrics(font)
    rect = QRect(0, 0, metrics.horizontalAdvance("hello world") + 2, metrics.lineSpacing() * 4)
    layout = wrap_option_text("hello world\n你好🙂\n下一行", font, rect)
    assert layout.lines == ("hello world", "你好🙂", "下一行")
    assert not layout.clipped


def test_a_grapheme_wider_than_the_available_space_is_marked_for_fulltext(qapp):
    font = qapp.font()
    layout = wrap_option_text("🙂", font, QRect(0, 0, 1, QFontMetrics(font).lineSpacing()))
    assert layout.clipped


def test_overflow_hover_is_plain_transparent_scrollable_and_does_not_reset_on_movement(application):
    text = "<b>补充选项</b>\n" + "\n".join(f"完整内容第 {i} 行" for i in range(60))
    widget = load_options(application, ["一", text, "三", "四"])
    point = widget.option_layouts()[1].rect.center()
    QTest.mouseMove(widget, point)
    QApplication.processEvents()
    bubble = widget._tooltip
    assert bubble.isVisible()
    assert bubble.text.toPlainText() == text
    assert not bubble.geometry().intersects(application.overlay.geometry())
    assert application.overlay.screen().availableGeometry().contains(bubble.geometry())
    event = QWheelEvent(
        QPointF(point),
        QPointF(widget.mapToGlobal(point)),
        QPoint(),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    scrollbar = bubble.text.verticalScrollBar()
    position = scrollbar.value()
    assert position > 0
    QTest.mouseMove(widget, point + QPoint(0, 1))
    assert scrollbar.value() == position
    application.preferences.set_color("background", QColor("#20203040"))
    application.apply_settings()
    QTest.mouseMove(widget, point + QPoint(0, 2))
    assert bubble.grab().toImage().pixelColor(bubble.width() // 2, 12).alpha() == 32
    QTest.mouseMove(widget, widget.rect().center())
    assert not bubble.isVisible()


def test_switching_questions_hides_option_fulltext(application):
    widget = load_options(application, ["一", "说明；" * 50, "三", "四"])
    QTest.mouseMove(widget, widget.option_layouts()[1].rect.center())
    assert widget._tooltip.isVisible()
    application.controller.load_questions(SAMPLE_QUESTIONS)
    assert widget._tooltip.isHidden()

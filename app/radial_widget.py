"""Paints the session and emits user intent; business state lives in QuizSession."""

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .config import AppSettings
from .geometry import RadialMetrics, bubble_position, option_angle, option_index, sector_angle
from .option_layout import OptionTextLayout, fit_option_text, sector_text_rects
from .questions import SAMPLE_QUESTIONS
from .session import QuizSession
from .text_dialog import ExplanationBubble


class RadialWidget(QWidget):
    option_selected = Signal(str)
    confirm_requested = Signal()
    navigation_selected = Signal(str)
    extension_requested = Signal()
    extension_hover_changed = Signal(bool)
    extension_scrolled = Signal(int)

    def __init__(self, session: QuizSession | None = None) -> None:
        super().__init__()
        self.session = session or QuizSession(SAMPLE_QUESTIONS)
        self.metrics = RadialMetrics()
        self.preferences = AppSettings()
        self.highlighted: int | None = None
        self._info_hovered = False
        self.nav_radius = 6
        self._tooltip = ExplanationBubble(self)
        self._tooltip.setWindowTitle("选项全文")
        self._tooltip_option: int | None = None
        self._tooltip.hide()
        self._rect_cache: dict[tuple, tuple[QRect, ...]] = {}
        self._layout_key: tuple | None = None
        self._layouts: tuple[OptionTextLayout, ...] = ()
        self.setFixedSize(self.metrics.size, self.metrics.size)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    @property
    def question(self):
        return self.session.question

    def apply_settings(self, preferences: AppSettings) -> None:
        self.preferences = preferences
        self._tooltip.apply_theme(preferences.theme)
        self.hide_tooltip()
        self.update()

    def reset_visuals(self) -> None:
        self.set_info_hover(False)
        self.highlighted = None
        self.hide_tooltip()
        self.update()

    def hide_tooltip(self) -> None:
        self._tooltip.hide()
        self._tooltip_option = None

    def set_info_hover(self, visible: bool) -> None:
        if visible != self._info_hovered:
            self._info_hovered = visible
            self.extension_hover_changed.emit(visible)
            self.update()

    def sector_angle(self) -> float:
        return sector_angle(len(self.question.options))

    def option_angle(self, index: int) -> float:
        return option_angle(index, len(self.question.options))

    def card_rect(self) -> QRect:
        center = self.rect().center()
        return QRect(
            center.x() - self.metrics.center_card_width // 2,
            center.y() - self.metrics.center_card_height // 2,
            self.metrics.center_card_width,
            self.metrics.center_card_height,
        )

    def corner_centers(self) -> tuple[QPoint, ...]:
        card, inset = self.card_rect(), self.nav_radius + 3
        return (
            QPoint(card.left() + inset, card.top() + inset),
            QPoint(card.right() - inset, card.top() + inset),
            QPoint(card.left() + inset, card.bottom() - inset),
            QPoint(card.right() - inset, card.bottom() - inset),
        )

    def corner_at(self, point: QPoint) -> str | None:
        names = ("extension", "confirm", "previous", "next")
        for name, center in zip(names, self.corner_centers()):
            if name == "extension" and self.question.extension is None:
                continue
            if math.hypot(point.x() - center.x(), point.y() - center.y()) <= self.nav_radius:
                return name
        return None

    def option_at(self, point: QPoint) -> int | None:
        if self.card_rect().contains(point):
            return None
        center = self.rect().center()
        return option_index(
            point.x() - center.x(),
            point.y() - center.y(),
            len(self.question.options),
            self.metrics.outer_radius,
        )

    def show_tooltip(self, index: int, point: QPoint) -> None:
        text = self.question.options[index].text
        layout = self.option_layouts()[index]
        if not layout.clipped:
            self.hide_tooltip()
            return
        if self._tooltip_option == index and self._tooltip.isVisible():
            return
        self._tooltip.set_text(text)
        global_point = self.mapToGlobal(point)
        screen = QApplication.screenAt(global_point) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self._tooltip.fit_to_screen(area.size())
            angle = math.radians(self.option_angle(index))
            preferred = (
                ("right" if math.cos(angle) > 0 else "left")
                if abs(math.cos(angle)) > abs(math.sin(angle))
                else ("bottom" if math.sin(angle) > 0 else "top")
            )
            anchor = QRect(self.mapToGlobal(QPoint()), self.size())
            target = self.mapToGlobal(layout.rect.center())
            position, direction = bubble_position(
                anchor, area, self._tooltip.size(), preferred, target
            )
            self._tooltip.direction = direction
            offset = target - position
            self._tooltip.tip = (
                max(20, min(offset.y(), self._tooltip.height() - 20))
                if direction in {"left", "right"}
                else max(20, min(offset.x(), self._tooltip.width() - 20))
            )
            self._tooltip.move(position)
        self._tooltip_option = index
        self._tooltip.show()
        self._tooltip.raise_()

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        self.set_info_hover(
            self.corner_at(point) == "extension"
            and self.question.extension is not None
            and self.question.extension.type == "info"
        )
        option = self.option_at(point)
        if option != self.highlighted:
            self.highlighted = option
            self.update()
        if option is None:
            self.hide_tooltip()
        else:
            self.show_tooltip(option, point)

    def leaveEvent(self, event) -> None:
        self.set_info_hover(False)
        self.highlighted = None
        self.hide_tooltip()
        self.update()
        super().leaveEvent(event)

    def hideEvent(self, event) -> None:
        self.set_info_hover(False)
        self.hide_tooltip()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        corner = self.corner_at(point)
        if corner == "confirm":
            self.confirm_requested.emit()
        elif corner == "extension":
            if self.question.extension.type != "info":
                self.extension_requested.emit()
        elif corner in {"previous", "next"}:
            self.navigation_selected.emit(corner)
        else:
            index = self.option_at(point)
            if index is not None:
                self.option_selected.emit(self.question.options[index].id)

    def wheelEvent(self, event) -> None:
        if self._info_hovered:
            self.extension_scrolled.emit(event.angleDelta().y())
            event.accept()
        elif self._tooltip.isVisible():
            self._tooltip.scroll_text(event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

    def ring_sector(self, center: QPoint, start: float, end: float) -> QPainterPath:
        outer, inner = self.metrics.outer_radius, self.metrics.inner_radius

        def point(radius: float, angle: float) -> QPointF:
            radians = math.radians(angle)
            return QPointF(
                center.x() + radius * math.cos(radians), center.y() + radius * math.sin(radians)
            )

        path = QPainterPath()
        path.moveTo(point(outer, start))
        path.arcTo(
            QRectF(center.x() - outer, center.y() - outer, 2 * outer, 2 * outer),
            -start,
            start - end,
        )
        path.lineTo(point(inner, end))
        path.arcTo(
            QRectF(center.x() - inner, center.y() - inner, 2 * inner, 2 * inner), -end, end - start
        )
        path.closeSubpath()
        return path

    def option_rects(self, center: QPoint, angle: float) -> tuple[QRect, ...]:
        line_height = self.fontMetrics().lineSpacing()
        key = (center.x(), center.y(), angle, self.sector_angle(), line_height)
        if key not in self._rect_cache:
            region = self.ring_sector(
                center, angle - self.sector_angle() / 2, angle + self.sector_angle() / 2
            )
            inset = QPainterPathStroker()
            inset.setWidth(4)
            region = region.subtracted(inset.createStroke(region))
            card = QPainterPath()
            card.addRect(QRectF(self.card_rect().adjusted(-3, -3, 3, 3)))
            region = region.subtracted(card)
            self._rect_cache[key] = sector_text_rects(
                region,
                center,
                angle,
                self.sector_angle(),
                self.metrics.inner_radius,
                self.metrics.outer_radius,
                line_height,
            )
        return self._rect_cache[key]

    def option_layouts(self) -> tuple[OptionTextLayout, ...]:
        key = (self.question, self.font().toString(), self.fontMetrics().lineSpacing())
        if key != self._layout_key:
            center = self.rect().center()
            self._layouts = tuple(
                fit_option_text(
                    option.text,
                    self.font(),
                    self.option_rects(center, self.option_angle(index)),
                    center,
                    self.option_angle(index),
                    self.sector_angle(),
                )
                for index, option in enumerate(self.question.options)
            )
            self._layout_key = key
        return self._layouts

    def option_color(self, index: int) -> str | None:
        selected = self.question.options[index].id in self.session.selected
        if selected and self.session.feedback in {"correct", "incorrect"}:
            return self.session.feedback + "_background"
        if selected:
            return "selected_background"
        return "hover_background" if index == self.highlighted else None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Keep the transparent outer rectangle hit-testable on Windows.
        painter.fillRect(self.rect(), QColor(255, 255, 255, 1))
        center, theme = self.rect().center(), self.preferences.theme
        painter.setFont(self.font())
        layouts = self.option_layouts()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(theme.color("outline"), 1))
        painter.drawEllipse(center, self.metrics.outer_radius, self.metrics.outer_radius)
        for index, option in enumerate(self.question.options):
            angle = self.option_angle(index)
            color = self.option_color(index)
            painter.setBrush(theme.color(color) if color else Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.color("outline"), 1))
            painter.drawPath(
                self.ring_sector(
                    center, angle - self.sector_angle() / 2, angle + self.sector_angle() / 2
                )
            )
            painter.setPen(theme.color("text"))
            layout = layouts[index]
            top = (
                layout.rect.top()
                + (layout.rect.height() - len(layout.lines) * layout.line_height) // 2
            )
            painter.save()
            painter.setClipRect(layout.rect)
            for row, text in enumerate(layout.lines):
                rect = QRect(
                    layout.rect.left(),
                    top + row * layout.line_height,
                    layout.rect.width(),
                    layout.line_height,
                )
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()

        card = self.card_rect()
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(card), 18, 18)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillPath(card_path, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.fillPath(card_path, theme.color("background"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(theme.color("outline"), 1))
        painter.drawRoundedRect(card, 18, 18)
        font = QFont(self.font())
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(theme.color("text"))
        painter.drawText(
            card.adjusted(17, 20, -17, -51),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.question.prompt,
        )
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            card.adjusted(15, 72, -15, -24),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            self.question.subtitle,
        )
        label = self.session.rules.get(self.question.mode).label
        painter.drawText(
            QRect(card.left(), card.bottom() - 13, card.width(), 12),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )
        for name, button_center, symbol in zip(
            ("extension", "confirm", "previous", "next"),
            self.corner_centers(),
            ("?", "✓", "‹", "›"),
        ):
            if name == "extension" and self.question.extension is None:
                continue
            painter.setBrush(
                theme.color("hover_background")
                if name == "extension" and self._info_hovered
                else Qt.BrushStyle.NoBrush
            )
            painter.setPen(QPen(theme.color("outline"), 1))
            painter.drawEllipse(button_center, self.nav_radius, self.nav_radius)
            painter.setPen(theme.color("text"))
            painter.drawText(
                QRect(button_center.x() - 6, button_center.y() - 6, 12, 12),
                Qt.AlignmentFlag.AlignCenter,
                symbol,
            )

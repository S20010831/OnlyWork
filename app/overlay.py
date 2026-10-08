import logging
import math

from PySide6.QtCore import QAbstractAnimation, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from .config import AppSettings
from .geometry import overlay_top_left
from .radial_widget import RadialWidget
from .session import QuizSession

logger = logging.getLogger(__name__)


class Overlay(QWidget):
    def __init__(self, session: QuizSession | None = None) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.widget = RadialWidget(session)
        self.widget.setParent(self)
        self.setFixedSize(self.widget.metrics.size, self.widget.metrics.size)
        self.widget.setGeometry(self.rect())
        self.widget.show()
        self.preferences = AppSettings()
        self._watch = QTimer(self)
        self._watch.setInterval(25)
        self._watch.timeout.connect(self.check_cursor)
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.timeout.connect(self.arm_cursor_watch)
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.timeout.connect(self.fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.finished.connect(self.finish_hide)
        self._armed = False
        self._cursor_entered = False

    def apply_settings(self, preferences: AppSettings) -> None:
        self.preferences = preferences
        self.widget.apply_settings(preferences)

    def show_at_cursor(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        self.move(overlay_top_left(QCursor.pos(), screen.availableGeometry(), self.width()))
        self._fade.stop()
        self._watch.stop()
        self._leave_timer.stop()
        self._arm_timer.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.widget.show()
        self._armed = False
        self._cursor_entered = False
        self._arm_timer.start(self.preferences.behavior.cursor_arm_delay_ms)
        logger.info("overlay shown geometry=%s", self.geometry())

    def arm_cursor_watch(self) -> None:
        if self.isVisible():
            self._armed = True
            self._watch.start()

    def check_cursor(self) -> None:
        if not self._armed or not self.isVisible():
            return
        point, center = self.mapFromGlobal(QCursor.pos()), self.rect().center()
        inside = (
            math.hypot(point.x() - center.x(), point.y() - center.y())
            <= self.widget.metrics.outer_radius
        )
        if inside:
            self._cursor_entered = True
            self._leave_timer.stop()
            if self._fade.state() == QAbstractAnimation.State.Running:
                self._fade.stop()
                self.setWindowOpacity(1.0)
        elif (
            self._cursor_entered
            and not self._leave_timer.isActive()
            and self._fade.state() != QAbstractAnimation.State.Running
        ):
            delay = self.preferences.behavior.hide_delay_ms
            if delay:
                self._leave_timer.start(delay)
            else:
                self.fade_out()

    def fade_out(self) -> None:
        self.widget.hide_tooltip()
        self._fade.stop()
        self._fade.setDuration(self.preferences.behavior.fade_duration_ms)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()
        logger.info("overlay fade started")

    def finish_hide(self) -> None:
        self.hide()
        self.setWindowOpacity(1.0)
        logger.info("overlay hidden")

    def hideEvent(self, event) -> None:
        self._watch.stop()
        self._arm_timer.stop()
        self._leave_timer.stop()
        self._fade.stop()
        self._armed = False
        self.widget.hide_tooltip()
        super().hideEvent(event)

    def shutdown(self) -> None:
        self.hide()

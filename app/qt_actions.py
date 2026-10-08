"""Qt implementation of the action host; media is created only when needed."""

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

from .extensions import ActionError, validate_url
from .geometry import bubble_position
from .text_dialog import ExplanationBubble
from .theme import ThemeColors


class QtActionContext(QObject):
    def __init__(
        self, parent: QWidget, base_directory: Path, on_error: Callable[[str], None]
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.base_directory = base_directory
        self.on_error = on_error
        self._info_dialog: ExplanationBubble | None = None
        self._theme = ThemeColors()
        self._player = None
        self._audio_output = None

    def show_info(self, text: str) -> None:
        if self._info_dialog is None:
            self._info_dialog = ExplanationBubble()
            self._info_text = self._info_dialog.text
            self._info_dialog.apply_theme(self._theme)
        self._info_dialog.set_text(text)
        if not self._info_dialog.isVisible():
            screen = self.parent_widget.screen().availableGeometry()
            self._info_dialog.fit_to_screen(screen.size())
            anchor = self.parent_widget.geometry()
            point, direction = bubble_position(anchor, screen, self._info_dialog.size())
            self._info_dialog.direction = direction
            offset = anchor.center() - point
            self._info_dialog.tip = (
                max(20, min(offset.y(), self._info_dialog.height() - 20))
                if direction in {"right", "left"}
                else max(20, min(offset.x(), self._info_dialog.width() - 20))
            )
            self._info_dialog.move(point)
        self._info_dialog.show()
        self._info_dialog.raise_()

    def hide_info(self) -> None:
        if self._info_dialog is not None:
            self._info_dialog.hide()

    def scroll_info(self, delta: int) -> None:
        if self._info_dialog is not None and self._info_dialog.isVisible():
            self._info_dialog.scroll_text(delta)

    def apply_theme(self, theme: ThemeColors) -> None:
        self._theme = theme
        if self._info_dialog is not None:
            self._info_dialog.apply_theme(theme)

    def open_url(self, url: str) -> None:
        validate_url(url)
        if not QDesktopServices.openUrl(QUrl(url)):
            raise ActionError("系统未能打开该链接")

    def play_audio(self, path: Path) -> None:
        if not path.is_file():
            raise ActionError(f"音频文件不存在：{path}")
        if self._player is None:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._audio_output = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.errorOccurred.connect(
                lambda _error, message: self.on_error(f"音频播放失败：{message}")
            )
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._player.play()

    def shutdown(self) -> None:
        if self._player is not None:
            self._player.stop()
        if self._info_dialog is not None:
            self._info_dialog.close()

"""A readable import report and a discreet, transparent explanation bubble."""

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTextBlockFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .theme import ThemeColors


def css_color(color: QColor, minimum_alpha: int = 0) -> str:
    return (
        f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(color.alpha(), minimum_alpha)})"
    )


class ThemedTextDialog(QDialog):
    def __init__(self, title: str, caption: str, badge: str = "?") -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(380, 280)
        self.resize(500, 410)
        self._drag_offset: QPoint | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 18)
        self.panel = QFrame()
        self.panel.setObjectName("textPanel")
        outer.addWidget(self.panel)
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.panel.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(22, 20, 22, 12)
        layout.setSpacing(18)
        header = QHBoxLayout()
        mark = QLabel(badge)
        mark.setObjectName("badge")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(36, 36)
        header.addWidget(mark)
        labels = QVBoxLayout()
        labels.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("heading")
        self.caption = QLabel(caption)
        self.caption.setObjectName("caption")
        labels.addWidget(heading)
        labels.addWidget(self.caption)
        for label in (mark, heading, self.caption):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header.addLayout(labels, 1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setToolTip("关闭（Esc）")
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.text = QTextBrowser()
        self.text.setFrameShape(QFrame.Shape.NoFrame)
        self.text.setOpenExternalLinks(False)
        self.text.setOpenLinks(False)
        self.text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.text.viewport().setAutoFillBackground(False)
        layout.addWidget(self.text, 1)
        footer = QHBoxLayout()
        self.footer_note = QLabel("Esc 关闭")
        self.footer_note.setObjectName("caption")
        footer.addWidget(self.footer_note)
        footer.addStretch()
        self.size_grip = QSizeGrip(self)
        footer.addWidget(self.size_grip)
        layout.addLayout(footer)
        self.apply_theme(ThemeColors())

    def set_text(self, text: str) -> None:
        self.text.setPlainText(text)
        cursor = QTextCursor(self.text.document())
        cursor.select(QTextCursor.SelectionType.Document)
        block = QTextBlockFormat()
        block.setLineHeight(145, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.mergeBlockFormat(block)
        self.text.verticalScrollBar().setValue(0)

    def apply_theme(self, theme: ThemeColors) -> None:
        self.theme = theme
        background = css_color(theme.color("background"), 242)
        text = css_color(theme.color("text"), 215)
        border = css_color(theme.color("outline"), 52)
        accent = css_color(theme.color("hover_background"), 32)
        muted = theme.color("text")
        muted.setAlpha(145)
        self.setStyleSheet(f"""
            QDialog {{ background: transparent; }}
            QFrame#textPanel {{ background: {background}; border: 1px solid {border};
                               border-radius: 20px; }}
            QLabel {{ color: {text}; background: transparent; border: none; }}
            QLabel#heading {{ font-size: 17px; font-weight: 600; }}
            QLabel#caption {{ color: {css_color(muted)}; font-size: 11px; }}
            QLabel#badge {{ background: {accent}; border: 1px solid {border};
                           border-radius: 12px; font-size: 21px; }}
            QTextBrowser {{ color: {text}; background: rgba(127, 152, 190, 9);
                            border: 1px solid {border}; border-radius: 12px;
                            padding: 12px; font-size: 13px; selection-background-color: {accent}; }}
            QPushButton#closeButton {{ color: {css_color(muted)}; background: transparent;
                                      border: none; border-radius: 9px; font-size: 20px; }}
            QPushButton#closeButton:hover {{ color: {text}; background: {accent}; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 6px 0; }}
            QScrollBar::handle:vertical {{ background: {border}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 94:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class ExplanationBubble(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setWindowTitle("题目解析")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        self.text = QTextBrowser()
        self.text.setFrameShape(QFrame.Shape.NoFrame)
        self.text.setOpenExternalLinks(False)
        self.text.setOpenLinks(False)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.text.viewport().setAutoFillBackground(False)
        font = QFont(self.font())
        font.setPointSize(8)
        self.text.setFont(font)
        self.text.document().setDocumentMargin(0)
        layout.addWidget(self.text)
        self.direction = "right"
        self.tip = 32
        self.apply_theme(ThemeColors())

    def set_text(self, text: str) -> None:
        self.text.setPlainText(text)
        cursor = QTextCursor(self.text.document())
        cursor.select(QTextCursor.SelectionType.Document)
        block = QTextBlockFormat()
        block.setLineHeight(135, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.mergeBlockFormat(block)
        self.text.verticalScrollBar().setValue(0)

    def fit_to_screen(self, available: QSize) -> None:
        width = min(260, available.width())
        self.text.document().setTextWidth(max(1, width - 40))
        height = max(64, math.ceil(self.text.document().size().height()) + 32)
        self.resize(width, min(height, 240, available.height()))

    def apply_theme(self, theme: ThemeColors) -> None:
        self.theme = theme
        self.setStyleSheet(f"""
            QTextBrowser {{ color: {css_color(theme.color("text"))};
                            background: transparent; border: none; padding: 0; }}
        """)
        self.update()

    def scroll_text(self, delta: int) -> None:
        scrollbar = self.text.verticalScrollBar()
        scrollbar.setValue(scrollbar.value() - round(delta / 120) * scrollbar.singleStep() * 3)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.theme.color("background"))
        painter.setPen(QPen(self.theme.color("outline"), 1))
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()).adjusted(8.5, 8.5, -8.5, -8.5), 12, 12)
        x, y = self.tip, self.tip
        triangles = {
            "right": [(9, y - 5), (2, y), (9, y + 5)],
            "left": [(self.width() - 9, y - 5), (self.width() - 2, y), (self.width() - 9, y + 5)],
            "bottom": [(x - 5, 9), (x, 2), (x + 5, 9)],
            "top": [
                (x - 5, self.height() - 9),
                (x, self.height() - 2),
                (x + 5, self.height() - 9),
            ],
        }
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(x, y) for x, y in triangles[self.direction]]))
        tail.closeSubpath()
        painter.drawPath(shape.united(tail))

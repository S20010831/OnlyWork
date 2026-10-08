import shutil

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import SettingsManager
from .paths import application_directory
from .questions import QuestionImporters

COLOR_FIELDS = (
    ("hover_background", "悬停背景色", "鼠标移动到选项时"),
    ("selected_background", "选中背景色", "点击后暂存选择"),
    ("correct_background", "答对提示色", "确认答案正确时"),
    ("incorrect_background", "答错提示色", "确认答案错误时"),
    ("text", "字体颜色", "题目、选项和按钮"),
    ("background", "背景颜色", "中心卡片背景"),
    ("outline", "线框颜色", "圆盘和卡片边框"),
)
BEHAVIOR_FIELDS = (
    ("feedback_delay_ms", "答对后切题时间", "自动进入下一道复习题", 100, 10000, " ms"),
    ("hide_delay_ms", "离开后隐藏延迟", "移回圆盘可取消隐藏", 0, 3000, " ms"),
)


class SettingsDialog(QDialog):
    import_requested = Signal(str)
    preferences_changed = Signal()
    error = Signal(str)

    def __init__(
        self, manager: SettingsManager, importers: QuestionImporters, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.manager, self.importers = manager, importers
        self.setWindowTitle("OnlyWork · 设置")
        self.setMinimumSize(520, 560)
        self.resize(600, 720)
        self.setStyleSheet("""
            QDialog, QScrollArea, QWidget#body { background: #111722; color: #dce6f2; }
            QScrollArea { border: none; }
            QLabel { color: #c4cfde; }
            QLabel#title { color: #f3f6fb; font-size: 20px; font-weight: 600; }
            QLabel#subtitle { color: #8492a7; font-size: 11px; }
            QGroupBox { border: 1px solid #293548; border-radius: 10px; margin-top: 14px;
                        padding: 12px 10px 10px; color: #dce6f2; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QPushButton { background: #1a2433; color: #dce6f2; border: 1px solid #34445c;
                          border-radius: 6px; padding: 7px 12px; }
            QPushButton:hover { background: #24334a; border-color: #52739e; }
            QPushButton#colorButton { padding: 4px 8px; }
            QPushButton#primary { background: #385779; border-color: #6389b7; }
            QSpinBox { background: #0d131d; color: #dce6f2; border: 1px solid #34445c;
                       border-radius: 5px; padding: 5px; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("body")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        title = QLabel("OnlyWork")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("调整刷题浮层的外观、交互与题库")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        appearance = QGroupBox("外观颜色")
        colors_grid = QGridLayout(appearance)
        self.color_buttons: dict[str, QPushButton] = {}
        for row, (field, label, description) in enumerate(COLOR_FIELDS):
            hint = QLabel(description)
            hint.setObjectName("subtitle")
            button = QPushButton()
            button.setObjectName("colorButton")
            button.setFixedWidth(128)
            button.clicked.connect(lambda _checked=False, name=field: self.choose_color(name))
            self.color_buttons[field] = button
            colors_grid.addWidget(QLabel(label), row, 0)
            colors_grid.addWidget(hint, row, 1)
            colors_grid.addWidget(button, row, 2)
        colors_grid.setColumnStretch(1, 1)
        layout.addWidget(appearance)

        behavior = QGroupBox("交互")
        grid = QGridLayout(behavior)
        self.behavior_inputs: dict[str, QSpinBox] = {}
        for row, (field, label, description, low, high, suffix) in enumerate(BEHAVIOR_FIELDS):
            hint = QLabel(description)
            hint.setObjectName("subtitle")
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(getattr(manager.behavior, field))
            spin.setSuffix(suffix)
            spin.valueChanged.connect(lambda value, name=field: self.change_behavior(name, value))
            self.behavior_inputs[field] = spin
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(hint, row, 1)
            grid.addWidget(spin, row, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(behavior)

        library = QGroupBox("题库")
        library_layout = QVBoxLayout(library)
        self.path_label = QLabel()
        self.path_label.setObjectName("subtitle")
        self.path_label.setWordWrap(True)
        import_button = QPushButton("导入题库")
        import_button.setObjectName("primary")
        import_button.clicked.connect(self.import_questions)
        library_layout.addWidget(self.path_label)
        library_layout.addWidget(import_button, alignment=Qt.AlignmentFlag.AlignLeft)
        template_button = QPushButton("保存空白模板")
        template_button.clicked.connect(self.save_template)
        library_layout.addWidget(template_button, alignment=Qt.AlignmentFlag.AlignLeft)
        template_hint = QLabel("另存模板并填写后导入；不同文件独立保存学习进度")
        template_hint.setObjectName("subtitle")
        template_hint.setWordWrap(True)
        library_layout.addWidget(template_hint)
        layout.addWidget(library)
        layout.addStretch()
        actions = QHBoxLayout()
        reset = QPushButton("恢复默认颜色")
        reset.clicked.connect(self.reset_theme)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        actions.addWidget(reset)
        actions.addStretch()
        actions.addWidget(close)
        outer.addLayout(actions)
        self.refresh_colors()

    def set_library(self, name: str, count: int) -> None:
        self.path_label.setText(f"当前题库：{name}\n共 {count} 道题，重启后自动恢复")

    def refresh_colors(self) -> None:
        for field, button in self.color_buttons.items():
            value = self.manager.colors.color(field).name(QColor.NameFormat.HexArgb).upper()
            button.setText(value)
            button.setStyleSheet(
                f"QPushButton#colorButton {{ background-color: {value}; color: white; }}"
            )

    def choose_color(self, field: str) -> None:
        color = QColorDialog.getColor(
            self.manager.colors.color(field),
            self,
            "选择颜色",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            try:
                self.manager.set_color(field, color)
            except (OSError, ValueError) as error:
                self.error.emit(f"颜色保存失败：{error}")
                return
            self.refresh_colors()
            self.preferences_changed.emit()

    def reset_theme(self) -> None:
        try:
            self.manager.reset_colors()
        except OSError as error:
            self.error.emit(f"颜色保存失败：{error}")
            return
        self.refresh_colors()
        self.preferences_changed.emit()

    def change_behavior(self, name: str, value: int) -> None:
        try:
            self.manager.set_behavior(**{name: value})
        except (OSError, ValueError) as error:
            with QSignalBlocker(self.behavior_inputs[name]):
                self.behavior_inputs[name].setValue(getattr(self.manager.behavior, name))
            self.error.emit(f"设置保存失败：{error}")
            return
        self.preferences_changed.emit()

    def import_questions(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择题库", "", self.importers.file_filter)
        if path:
            self.import_requested.emit(path)

    def save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存题库模板", "我的题库.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            shutil.copy2(application_directory() / "examples" / "question-template.xlsx", path)
        except OSError as error:
            self.error.emit(f"模板保存失败：{error}")
            return
        QMessageBox.information(self, "模板已保存", "在“轮盘题库”中填写题目，填写说明页提供示例。")

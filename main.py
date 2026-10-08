import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from app.config import DATA_DIR, SettingsManager
from app.controller import StudyController
from app.input_service import GlobalHotkey
from app.library import LibraryStore
from app.models import ImportValidationError
from app.overlay import Overlay
from app.paths import LOG_PATH, resource_path
from app.qt_actions import QtActionContext
from app.scheduler import ReviewScheduler
from app.services import AppServices
from app.session import QuizSession
from app.storage import preserve_file
from app.text_dialog import ThemedTextDialog
from app.version import __version__

logger = logging.getLogger(__name__)


class App:
    def __init__(
        self,
        application: QApplication,
        data_dir: Path | None = None,
        services: AppServices | None = None,
        start_services: bool = True,
    ) -> None:
        from app.settings import SettingsDialog

        self.application = application
        self.services = services or AppServices()
        data_dir = data_dir or DATA_DIR
        self.preferences = SettingsManager(data_dir / "settings.json")
        self.library_store = LibraryStore(
            data_dir / "library.json",
            self.services.importers,
            self.services.actions,
            self.services.answers,
        )
        self.library = self.library_store.load()
        self.session = QuizSession(self.library.questions, self.services.answers)
        self.overlay = Overlay(self.session)
        self.action_context = QtActionContext(self.overlay, data_dir, self.report_error)
        self.scheduler = ReviewScheduler(
            data_dir / "review_state.json",
            self.services.review_strategy,
            self.services.spacing_policy,
            bank_id=self.library.id,
        )
        self.controller = StudyController(
            self.session,
            self.scheduler,
            self.services.actions,
            self.action_context,
            self.preferences.behavior.feedback_delay_ms,
            self.overlay,
        )
        self.settings = SettingsDialog(self.preferences, self.services.importers)
        self.settings.set_library(self.library.name, len(self.library.questions))
        self.settings.import_requested.connect(self.import_library)
        self.settings.preferences_changed.connect(self.apply_settings)
        self.settings.error.connect(self.report_error)
        widget = self.overlay.widget
        widget.option_selected.connect(self.controller.select_option)
        widget.confirm_requested.connect(self.controller.confirm_answer)
        widget.navigation_selected.connect(self.controller.navigate_question)
        widget.extension_requested.connect(self.controller.run_extension)
        widget.extension_hover_changed.connect(self.preview_info)
        widget.extension_scrolled.connect(self.action_context.scroll_info)
        self.controller.changed.connect(widget.update)
        self.controller.question_changed.connect(widget.reset_visuals)
        self.controller.question_changed.connect(self.action_context.hide_info)
        self.controller.error.connect(self.report_error)
        self.import_error_dialog: ThemedTextDialog | None = None
        self.apply_settings()
        self.hotkey = GlobalHotkey()
        self.hotkey.triggered.connect(self.show)
        icon_path = resource_path("icon/onlywork.png")
        icon = QIcon(str(icon_path))
        if icon.isNull():
            icon = application.style().standardIcon(
                application.style().StandardPixmap.SP_ComputerIcon
            )
        application.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, application)
        self.tray.setToolTip(f"OnlyWork {__version__}")
        self.tray_menu = QMenu()
        for title, callback in (
            ("设置 / 导入题库", self.open_settings),
            ("显示径向界面", self.show),
        ):
            action = QAction(title, self.tray_menu)
            action.triggered.connect(callback)
            self.tray_menu.addAction(action)
        self.tray_menu.addSeparator()
        quit_action = QAction("退出", self.tray_menu)
        quit_action.triggered.connect(application.quit)
        self.tray_menu.addAction(quit_action)
        self.tray.setContextMenu(self.tray_menu)
        if start_services:
            self.tray.show()
            self.hotkey.start()
            if not self.hotkey.registered:
                self.tray.showMessage(
                    "快捷键不可用", "可通过托盘菜单显示圆盘。", QSystemTrayIcon.MessageIcon.Warning
                )
        logger.info(
            "app started library=%s questions=%s", self.library.name, len(self.library.questions)
        )

    def open_settings(self) -> None:
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def apply_settings(self) -> None:
        self.overlay.apply_settings(self.preferences.settings)
        self.action_context.apply_theme(self.preferences.colors)
        if self.import_error_dialog is not None:
            self.import_error_dialog.apply_theme(self.preferences.colors)
        self.controller.next_question_timer.setInterval(self.preferences.behavior.feedback_delay_ms)

    def show(self) -> None:
        self.overlay.show_at_cursor()

    def preview_info(self, visible: bool) -> None:
        action = self.session.question.extension
        if visible and action is not None and action.type == "info":
            self.action_context.show_info(action.value)
        else:
            self.action_context.hide_info()

    def import_library(self, path: str) -> None:
        try:
            library = self.library_store.prepare_import(path)
            with preserve_file(self.library_store.path), self.scheduler.transaction():
                self.scheduler.switch_bank(library.id)
                initial_index, _ = self.scheduler.resume(library.questions)
                self.library_store.save(library)
            self.controller.load_questions(library.questions, initial_index=initial_index)
        except ImportValidationError as error:
            self.report_import_errors(error)
            return
        except (OSError, ValueError, TypeError) as error:
            logger.warning("library import failed: %s", error, exc_info=True)
            self.report_error(f"题库导入失败：{error}")
            return
        self.library = library
        self.settings.set_library(library.name, len(library.questions))
        QMessageBox.information(
            self.settings, "导入成功", f"已导入并保存 {len(library.questions)} 道题。"
        )

    def report_import_errors(self, error: ImportValidationError) -> None:
        if self.import_error_dialog is None:
            self.import_error_dialog = ThemedTextDialog("题库需要修改", "", "!")
            self.import_error_dialog.resize(580, 460)
        self.import_error_dialog.caption.setText(f"共 {len(error.issues)} 处问题，修改后重新导入")
        self.import_error_dialog.apply_theme(self.preferences.colors)
        self.import_error_dialog.set_text(str(error))
        self.import_error_dialog.show()
        self.import_error_dialog.raise_()
        self.import_error_dialog.activateWindow()

    def report_error(self, message: str) -> None:
        parent = (
            self.settings
            if hasattr(self, "settings") and self.settings.isVisible()
            else self.overlay
        )
        QMessageBox.warning(parent, "OnlyWork", message)

    def shutdown(self) -> None:
        self.controller.shutdown()
        self.hotkey.stop()
        self.tray.hide()
        self.action_context.shutdown()
        if self.import_error_dialog is not None:
            self.import_error_dialog.close()
        self.settings.close()
        self.overlay.shutdown()


def main(services: AppServices | None = None) -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from app.smoke import run_smoke_test

        return run_smoke_test(App, Path(sys.argv[2]))
    logging.basicConfig(
        handlers=[
            RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        ],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    application = QApplication(sys.argv)
    application.setApplicationName("OnlyWork")
    application.setApplicationVersion(__version__)
    application.setQuitOnLastWindowClosed(False)
    lock = QLockFile(
        str(
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
            / "radial-study.lock"
        )
    )
    if not lock.tryLock(100):
        logger.warning("another OnlyWork instance is already running")
        return 0
    try:
        app = App(application, services=services)
    except Exception:
        logger.exception("application startup failed")
        raise
    application.aboutToQuit.connect(app.shutdown)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

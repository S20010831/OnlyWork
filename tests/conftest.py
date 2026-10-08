import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from main import App


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    # Windows offscreen Qt does not automatically discover the system fonts.
    path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
    if path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            application.setFont(QFont(families[0], 9))
    return application


@pytest.fixture
def application(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[-1]))
    instance = App(qapp, data_dir=tmp_path / "data", start_services=False)
    instance.test_warnings = warnings
    yield instance
    instance.shutdown()
    instance.settings.deleteLater()
    instance.overlay.deleteLater()
    instance.tray.deleteLater()
    instance.tray_menu.deleteLater()
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class FakeActionContext:
    def __init__(self, base_directory: Path):
        self.base_directory = base_directory
        self.info = []
        self.urls = []
        self.audio = []

    def show_info(self, text):
        self.info.append(text)

    def open_url(self, url):
        self.urls.append(url)

    def play_audio(self, path):
        self.audio.append(path)


@pytest.fixture
def action_context(tmp_path):
    return FakeActionContext(tmp_path)

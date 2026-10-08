import ctypes
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QSignalSpy

from app.extensions import ActionError
from app.input_service import HOTKEY_ID, WM_HOTKEY, GlobalHotkey, Win32Message


def test_native_hotkey_registration_event_and_cleanup(qapp, monkeypatch):
    api = MagicMock()
    api.RegisterHotKey.return_value = True
    monkeypatch.setattr("app.input_service.sys.platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api)
    hotkey = GlobalHotkey()
    spy = QSignalSpy(hotkey.triggered)
    try:
        hotkey.start()
        hotkey.start()
        assert hotkey.registered
        assert api.RegisterHotKey.call_count == 1
        message = Win32Message()
        message.message, message.wParam = WM_HOTKEY, HOTKEY_ID
        assert hotkey.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message)) == (
            True,
            0,
        )
        assert spy.count() == 1
    finally:
        hotkey.stop()
    hotkey.stop()
    assert api.UnregisterHotKey.call_count == 1
    assert not hotkey.registered


def test_failed_hotkey_registration_does_not_install_or_unregister(qapp, monkeypatch):
    api = MagicMock()
    api.RegisterHotKey.return_value = False
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api)
    hotkey = GlobalHotkey()
    hotkey.start()
    hotkey.stop()
    assert not hotkey.registered
    api.UnregisterHotKey.assert_not_called()


def test_browser_adapter_reports_system_failure(application, monkeypatch):
    urls = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: urls.append(url.toString()) or True
    )
    application.action_context.open_url("https://example.com")
    assert urls == ["https://example.com"]
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: False)
    with pytest.raises(ActionError):
        application.action_context.open_url("https://example.com")


def test_media_adapter_retains_player_and_reports_async_errors(application, tmp_path, monkeypatch):
    import PySide6.QtMultimedia as multimedia

    class FakeSignal:
        def connect(self, callback):
            self.callback = callback

    class FakePlayer:
        def __init__(self, parent):
            self.errorOccurred = FakeSignal()
            self.play_count = 0
            self.stop_count = 0

        def setAudioOutput(self, output):
            self.output = output

        def stop(self):
            self.stop_count += 1

        def setSource(self, url):
            self.source = url

        def play(self):
            self.play_count += 1

    monkeypatch.setattr(multimedia, "QMediaPlayer", FakePlayer)
    monkeypatch.setattr(multimedia, "QAudioOutput", lambda parent: object())
    audio = tmp_path / "sound.wav"
    audio.write_bytes(b"test asset")
    context = application.action_context
    context.play_audio(audio)
    player = context._player
    context.play_audio(audio)
    assert context._player is player and player.play_count == 2
    assert Path(player.source.toLocalFile()) == audio.resolve()
    player.errorOccurred.callback(1, "unsupported media")
    assert "unsupported media" in application.test_warnings[-1]
    context.shutdown()
    assert player.stop_count == 3

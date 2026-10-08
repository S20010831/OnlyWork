"""Windows hotkey adapter. Unsupported platforms retain the tray entry point."""

import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

logger = logging.getLogger(__name__)
WM_HOTKEY, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0312, 0x0002, 0x0004, 0x4000
VK_SPACE, HOTKEY_ID = 0x20, 1


class Win32Message(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


class GlobalHotkey(QObject, QAbstractNativeEventFilter):
    triggered = Signal()

    def __init__(self) -> None:
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self._registered = False
        self._user32 = None

    @property
    def registered(self) -> bool:
        return self._registered

    def start(self) -> None:
        if self._registered:
            return
        if sys.platform != "win32":
            logger.warning("native hotkey is only available on Windows")
            return
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._registered = bool(
            self._user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE
            )
        )
        if self._registered:
            QCoreApplication.instance().installNativeEventFilter(self)
            logger.info("global Ctrl+Shift+Space registered")
        else:
            logger.warning("RegisterHotKey failed: %s", ctypes.get_last_error())

    def stop(self) -> None:
        if self._registered:
            self._user32.UnregisterHotKey(None, HOTKEY_ID)
            instance = QCoreApplication.instance()
            if instance:
                instance.removeNativeEventFilter(self)
            self._registered = False

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = ctypes.cast(int(message), ctypes.POINTER(Win32Message)).contents
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.triggered.emit()
                return True, 0
        return False, 0

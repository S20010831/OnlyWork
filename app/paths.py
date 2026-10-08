"""Locate bundled resources and writable files without importing the UI toolkit."""

import sys
from pathlib import Path


def application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", application_directory()))
    return root / relative


DATA_DIR = application_directory() / "data"
LOG_PATH = application_directory() / "radial-study.log"

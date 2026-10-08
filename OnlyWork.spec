# Build on Windows using: python -m PyInstaller --noconfirm OnlyWork.spec
import os
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "icon" / "onlywork.png"), "icon")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PIL", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OnlyWork",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=bool(os.environ.get("ONLYWORK_BUILD_CONSOLE")),
    icon=str(root / "icon" / "onlywork.png"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="OnlyWork")

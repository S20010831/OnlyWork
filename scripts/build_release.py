"""Build, smoke-test, and zip the Windows portable release."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import distribution, version
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import __version__


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows releases must be built on Windows")
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and tag != f"v{__version__}":
        raise SystemExit("Release tag must match app/version.py")
    for directory in (ROOT / "build", ROOT / "dist", ROOT / "release"):
        if not directory.resolve().is_relative_to(ROOT):
            raise SystemExit(f"Build directory escapes the project: {directory}")
    # Keep unrelated command-line tools' DLL directories out of dependency discovery.
    windows = Path(os.environ["SYSTEMROOT"])
    build_environment = {
        **os.environ,
        "PATH": os.pathsep.join(
            str(directory)
            for directory in (
                Path(sys.executable).parent,
                Path(sys.base_prefix),
                windows / "System32",
                windows,
                distribution("PySide6").locate_file("PySide6"),
                distribution("shiboken6").locate_file("shiboken6"),
            )
        ),
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(ROOT / "OnlyWork.spec"),
        ],
        cwd=ROOT,
        env=build_environment,
        check=True,
    )
    package = ROOT / "dist" / "OnlyWork"
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "RELEASE_NOTES.md"):
        shutil.copy2(ROOT / name, package / name)
    for folder in ("examples", "docs"):
        shutil.copytree(ROOT / folder, package / folder, dirs_exist_ok=True)
    runtime_versions = {
        "Python": sys.version.split()[0],
        **{name: version(name) for name in ("PySide6", "shiboken6", "openpyxl", "et-xmlfile")},
    }
    (package / "runtime-versions.json").write_text(
        json.dumps(runtime_versions, indent=2), encoding="utf-8"
    )
    report = ROOT / "build" / "smoke-test.json"
    environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [str(package / "OnlyWork.exe"), "--smoke-test", str(report)],
        cwd=package,
        env=environment,
        timeout=60,
    )
    if result.returncode or not report.is_file():
        raise SystemExit("Packaged application smoke test failed")
    checks = json.loads(report.read_text(encoding="utf-8"))
    if not checks.get("ok"):
        raise SystemExit(checks.get("error", "Packaged application smoke test failed"))
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    archive = release / f"OnlyWork-{__version__}-windows-x64.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(package.rglob("*")):
            if file.is_file():
                if file.name.startswith("~$"):
                    continue
                output.write(file, Path("OnlyWork") / file.relative_to(package))
    with archive.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(f"Built {archive.name}; smoke test passed with {checks['questions']} example questions")


if __name__ == "__main__":
    main()

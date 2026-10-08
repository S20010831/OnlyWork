"""Exercise the packaged application without a tray, hotkey, or real study data."""

import json
import os
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

from .paths import application_directory, resource_path


def run_smoke_test(factory, report_path: Path) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = None
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtMultimedia import QMediaPlayer
        from PySide6.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with TemporaryDirectory(prefix="onlywork-smoke-") as folder:
            instance = factory(application, data_dir=Path(folder), start_services=False)
            if QIcon(str(resource_path("icon/onlywork.png"))).isNull():
                raise RuntimeError("Bundled application icon is missing")
            source = application_directory() / "examples" / "cet4-vocabulary.xlsx"
            library = instance.library_store.prepare_import(source)
            if len(library.questions) != 3848:
                raise RuntimeError("CET4 example is incomplete")
            instance.library_store.save(library)
            instance.scheduler.switch_bank(library.id)
            instance.controller.load_questions(library.questions)
            if instance.library_store.load() != library:
                raise RuntimeError("Imported library did not persist")
            if not (source.parent / "question-template.xlsx").is_file():
                raise RuntimeError("Blank question template is missing")
            instance.controller.navigate_question("next")
            resume_id = instance.session.question.id
            instance.scheduler.record(resume_id, False)
            instance.shutdown()
            instance = factory(application, data_dir=Path(folder), start_services=False)
            if instance.session.question.id != resume_id:
                raise RuntimeError("Study position did not resume after restart")
            if instance.scheduler.states[resume_id].incorrect != 1:
                raise RuntimeError("Answer count changed during restart")
            instance.scheduler.record("1", True)
            instance.scheduler.switch_bank("smoke-other")
            instance.scheduler.record("1", False)
            instance.scheduler.switch_bank(library.id)
            if instance.scheduler.states["1"].incorrect:
                raise RuntimeError("Question bank progress is not isolated")
            instance.action_context.show_info(library.questions[0].extension.value)
            application.processEvents()
            if not instance.action_context._info_dialog.isVisible():
                raise RuntimeError("Explanation bubble did not open")
            instance.action_context.hide_info()
            player = QMediaPlayer(instance.action_context)
            player.stop()
            result = {
                "ok": True,
                "questions": len(library.questions),
                "data_isolated": True,
                "bank_isolated": True,
                "restart_resumed": True,
                "info_preview": True,
            }
            instance.shutdown()
            instance = None
    except Exception:
        result = {"ok": False, "error": traceback.format_exc()}
    finally:
        if instance is not None:
            instance.shutdown()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1

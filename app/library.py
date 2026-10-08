"""Persist a normalized library and imported assets independently of source files."""

import logging
import os
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from .answers import AnswerRules, default_answer_rules
from .extensions import ActionRegistry, default_actions
from .models import ImportIssue, ImportValidationError, QuestionFormatError, QuizQuestion
from .paths import DATA_DIR
from .questions import (
    SAMPLE_QUESTIONS,
    QuestionImporters,
    default_importers,
    load_questions_from_json,
    question_to_dict,
    validate_unique,
)
from .storage import read_json, write_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuestionLibrary:
    name: str
    questions: tuple[QuizQuestion, ...]
    id: str


class LibraryStore:
    def __init__(
        self,
        path: Path | None = None,
        importers: QuestionImporters | None = None,
        actions: ActionRegistry | None = None,
        rules: AnswerRules | None = None,
    ) -> None:
        self.path = path or DATA_DIR / "library.json"
        self.importers = importers or default_importers()
        self.actions = actions or default_actions()
        self.rules = rules or default_answer_rules()

    def validate(self, questions: tuple[QuizQuestion, ...]) -> None:
        validate_unique(questions)
        issues = []
        for question in questions:
            location = (
                f"第 {question.source_row} 行" if question.source_row else f"ID {question.id}"
            )
            for validate in (
                lambda: self.rules.get(question.mode).validate(question),
                lambda: self.actions.validate(question.extension),
            ):
                try:
                    validate()
                except ValueError as error:
                    issues.append(ImportIssue(location, str(error)))
        if issues:
            raise ImportValidationError(tuple(issues))

    def load(self) -> QuestionLibrary:
        try:
            raw = read_json(self.path)
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("name"), str)
                or not isinstance(raw.get("library_id"), str)
                or not raw["library_id"]
            ):
                raise QuestionFormatError("题库缓存格式无效")
            questions = load_questions_from_json(self.path)
            self.validate(questions)
            return QuestionLibrary(raw["name"], questions, raw["library_id"])
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            logger.warning("saved library unavailable; using samples", exc_info=True)
        return QuestionLibrary("内置示例题库", SAMPLE_QUESTIONS, "builtin")

    def prepare_import(self, path: str | Path) -> QuestionLibrary:
        source = Path(path).resolve()
        try:
            questions = self.importers.load(source)
        except ImportValidationError as parse_error:
            issues = list(parse_error.issues)
            if parse_error.valid_questions:
                try:
                    self.validate(parse_error.valid_questions)
                except ImportValidationError as validation_error:
                    issues.extend(validation_error.issues)
            raise ImportValidationError(tuple(issues)) from parse_error
        self.validate(questions)
        prepared = tuple(
            replace(
                question,
                extension=self.actions.prepare(question.extension, source.parent, self.path.parent),
            )
            if question.extension
            else question
            for question in questions
        )
        identity = sha256(os.path.normcase(str(source)).encode("utf-8")).hexdigest()
        return QuestionLibrary(source.name, prepared, "file-" + identity)

    def save(self, library: QuestionLibrary) -> None:
        self.validate(library.questions)
        write_json(
            self.path,
            {
                "version": 1,
                "name": library.name,
                "library_id": library.id,
                "questions": [question_to_dict(question) for question in library.questions],
            },
        )

    def import_file(self, path: str | Path) -> QuestionLibrary:
        library = self.prepare_import(path)
        self.save(library)
        return library

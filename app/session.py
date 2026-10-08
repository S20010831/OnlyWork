"""The quiz state machine is independent of Qt and persistent storage."""

from dataclasses import dataclass

from .answers import AnswerRules, default_answer_rules
from .models import QuestionFormatError, QuizQuestion


@dataclass(frozen=True)
class Submission:
    question_id: str
    selected_ids: frozenset[str]
    correct: bool


class QuizSession:
    def __init__(
        self, questions: tuple[QuizQuestion, ...], rules: AnswerRules | None = None
    ) -> None:
        self.rules = rules or default_answer_rules()
        self.questions: tuple[QuizQuestion, ...] = ()
        self.index = 0
        self.selected = frozenset[str]()
        self.feedback: str | None = None
        self._revision = 0
        self._submitted_revision: int | None = None
        self.set_questions(questions)

    @property
    def question(self) -> QuizQuestion:
        return self.questions[self.index]

    def validate_questions(self, questions: tuple[QuizQuestion, ...]) -> None:
        if not questions:
            raise QuestionFormatError("题库没有题目")
        if len({question.id for question in questions}) != len(questions):
            raise QuestionFormatError("题目 ID 重复；相同题目请使用不同的 ID")
        for question in questions:
            self.rules.get(question.mode).validate(question)

    def set_questions(self, questions: tuple[QuizQuestion, ...]) -> None:
        self.validate_questions(questions)
        self.questions = tuple(questions)
        self.load(0)

    def load(self, index: int) -> None:
        self.index = index % len(self.questions)
        self.selected = frozenset()
        self.feedback = None
        self._revision += 1
        self._submitted_revision = None

    def select(self, option_id: str) -> bool:
        if self.feedback == "correct" or option_id not in {
            option.id for option in self.question.options
        }:
            return False
        self.selected = self.rules.get(self.question.mode).toggle(self.selected, option_id)
        self.feedback = None
        self._revision += 1
        return True

    def submit(self) -> Submission | None:
        if (
            not self.selected
            or self.feedback == "correct"
            or self._submitted_revision == self._revision
        ):
            return None
        correct = self.rules.get(self.question.mode).evaluate(self.question, self.selected)
        self.feedback = "correct" if correct else "incorrect"
        self._submitted_revision = self._revision
        return Submission(self.question.id, self.selected, correct)

    def cancel_submission(self) -> None:
        """Allow retry when the storage transaction fails."""
        self.feedback = None
        self._submitted_revision = None

"""Register answer rules here without changing the controller or painter."""

from dataclasses import dataclass
from typing import Protocol

from .models import QuestionFormatError, QuizQuestion


class AnswerRule(Protocol):
    label: str
    auto_submit: bool

    def validate(self, question: QuizQuestion) -> None: ...
    def toggle(self, selected: frozenset[str], option_id: str) -> frozenset[str]: ...
    def evaluate(self, question: QuizQuestion, selected: frozenset[str]) -> bool: ...


@dataclass(frozen=True)
class ChoiceRule:
    label: str
    auto_submit: bool = False
    single: bool = False

    def validate(self, question: QuizQuestion) -> None:
        if self.single and len(question.correct_ids) != 1:
            raise QuestionFormatError("单选题必须只有一个正确选项")

    def toggle(self, selected: frozenset[str], option_id: str) -> frozenset[str]:
        if self.single:
            return frozenset() if option_id in selected else frozenset({option_id})
        return selected ^ {option_id}

    def evaluate(self, question: QuizQuestion, selected: frozenset[str]) -> bool:
        return selected == question.correct_ids


class AnswerRules:
    def __init__(self) -> None:
        self._rules: dict[str, AnswerRule] = {}

    def register(self, name: str, rule: AnswerRule) -> None:
        if not name or name in self._rules:
            raise ValueError(f"题型已注册或名称为空：{name}")
        self._rules[name] = rule

    def get(self, name: str) -> AnswerRule:
        try:
            return self._rules[name]
        except KeyError as error:
            raise QuestionFormatError(f"不支持的题型：{name}") from error


def default_answer_rules() -> AnswerRules:
    rules = AnswerRules()
    rules.register("single", ChoiceRule("单选", auto_submit=True, single=True))
    rules.register("multiple", ChoiceRule("多选"))
    return rules

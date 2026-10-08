from dataclasses import replace

import pytest

from app.answers import ChoiceRule, default_answer_rules
from app.models import QuestionFormatError
from app.questions import SAMPLE_QUESTIONS
from app.session import QuizSession


def test_single_selection_replaces_previous_and_counts_each_changed_submission():
    session = QuizSession(SAMPLE_QUESTIONS)
    assert session.submit() is None
    session.select("B")
    assert session.submit().correct is False
    assert session.submit() is None
    session.select("A")
    assert session.selected == {"A"}
    assert session.submit().correct is True
    assert session.submit() is None
    assert session.select("C") is False


def test_single_option_can_be_cancelled_before_submission():
    session = QuizSession(SAMPLE_QUESTIONS)
    session.select("B")
    session.select("B")
    assert not session.selected
    assert session.submit() is None


def test_multiple_requires_exact_set_and_allows_correction():
    session = QuizSession(SAMPLE_QUESTIONS)
    session.load(1)
    session.select("A")
    assert session.submit().correct is False
    assert session.submit() is None
    for answer in ("B", "D"):
        session.select(answer)
    assert session.submit().correct is True
    session.load(-1)
    assert session.index == 1
    assert not session.selected and session.feedback is None


def test_invalid_bank_preserves_active_session():
    session = QuizSession(SAMPLE_QUESTIONS)
    with pytest.raises(QuestionFormatError):
        session.set_questions(())
    assert session.questions == SAMPLE_QUESTIONS
    with pytest.raises(QuestionFormatError):
        session.set_questions((replace(SAMPLE_QUESTIONS[1], mode="single"),))


def test_register_custom_question_rule_without_controller_changes():
    rules = default_answer_rules()
    rules.register("practice", ChoiceRule("练习", auto_submit=False, single=True))
    question = replace(SAMPLE_QUESTIONS[0], mode="practice")
    session = QuizSession((question,), rules)
    session.select("A")
    assert session.feedback is None
    assert session.submit().correct

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from app.questions import SAMPLE_QUESTIONS
from app.scheduler import ReviewScheduler, ReviewState, SpacedReviewPolicy, parse_time
from app.storage import read_json, write_json

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def make_scheduler(tmp_path, **kwargs):
    return ReviewScheduler(tmp_path / "review.json", clock=lambda: NOW, rng=Random(0), **kwargs)


def test_banks_isolate_matching_ids_and_restore_after_restart(tmp_path):
    scheduler = make_scheduler(tmp_path)
    scheduler.switch_bank("english")
    scheduler.record("1", True)
    scheduler.switch_bank("math")
    scheduler.record("1", False)
    assert scheduler.states["1"].incorrect == 1
    restored = make_scheduler(tmp_path)
    restored.switch_bank("english")
    assert restored.states["1"].correct == 1
    assert restored.states["1"].incorrect == 0
    restored.switch_bank("math")
    assert restored.states["1"].correct == 0
    assert read_json(restored.path)["version"] == 2


def test_correct_intervals_error_reset_and_reload(tmp_path):
    scheduler = make_scheduler(tmp_path)
    identifier = SAMPLE_QUESTIONS[0].id
    for expected in (1, 3, 7, 14, 30, 30):
        scheduler.record(identifier, True)
        assert scheduler.states[identifier].interval_days == expected
    scheduler.record(identifier, False)
    state = scheduler.states[identifier]
    assert state.streak == 0 and state.attempts == 7
    assert parse_time(state.due_at) == NOW + timedelta(minutes=5)
    assert make_scheduler(tmp_path).states[identifier].incorrect == 1


def test_choose_excludes_actual_current_question_and_handles_single_bank(tmp_path):
    scheduler = make_scheduler(tmp_path)
    current = SAMPLE_QUESTIONS[0].id
    assert scheduler.choose(SAMPLE_QUESTIONS, current)[1] != current
    assert scheduler.choose((SAMPLE_QUESTIONS[0],), current) == (0, current)
    assert scheduler.states[current].last_shown_at == NOW.isoformat()
    with pytest.raises(ValueError):
        scheduler.choose(())


def test_naive_timestamps_and_bad_entries_do_not_break_scheduler(tmp_path):
    value = asdict(ReviewState(SAMPLE_QUESTIONS[0].id, due_at="2026-01-01T12:00:00"))
    write_json(
        tmp_path / "review.json",
        {
            "version": 2,
            "banks": {"builtin": {SAMPLE_QUESTIONS[0].id: value, "bad": {"attempts": "wrong"}}},
        },
    )
    scheduler = make_scheduler(tmp_path)
    assert parse_time(scheduler.states[SAMPLE_QUESTIONS[0].id].due_at).tzinfo is not None
    assert "bad" not in scheduler.states
    scheduler.choose(SAMPLE_QUESTIONS)


def test_custom_strategy_and_spacing_policy_are_used(tmp_path):
    class PriorityStrategy:
        def score(self, state, current):
            return 100 if state.question_id == SAMPLE_QUESTIONS[1].id else 0.001

    scheduler = make_scheduler(
        tmp_path, strategy=PriorityStrategy(), policy=SpacedReviewPolicy((2, 4))
    )
    assert scheduler.choose(SAMPLE_QUESTIONS)[0] == 1
    scheduler.record(SAMPLE_QUESTIONS[1].id, True)
    assert scheduler.states[SAMPLE_QUESTIONS[1].id].interval_days == 2


def test_record_failure_rolls_back_in_memory(tmp_path, monkeypatch):
    scheduler = make_scheduler(tmp_path)
    scheduler.record("question", False)
    before = asdict(scheduler.states["question"])

    def fail(*args):
        raise PermissionError("locked")

    monkeypatch.setattr("app.scheduler.write_json", fail)
    with pytest.raises(PermissionError):
        scheduler.record("question", True)
    assert asdict(scheduler.states["question"]) == before


def test_sync_failure_restores_active_bank_and_keeps_other_banks(tmp_path, monkeypatch):
    scheduler = make_scheduler(tmp_path)
    scheduler.switch_bank("first")
    scheduler.record("1", True)
    scheduler.switch_bank("second")
    before = scheduler.path.read_bytes()

    def fail():
        raise PermissionError("locked")

    monkeypatch.setattr(scheduler, "save", fail)
    with pytest.raises(PermissionError):
        scheduler.sync_questions(SAMPLE_QUESTIONS)
    assert scheduler.states == {}
    assert scheduler.path.read_bytes() == before
    scheduler.switch_bank("first")
    assert scheduler.states["1"].correct == 1


@pytest.mark.parametrize("stored_position", [None, {"question_id": "bad", "completed": "yes"}])
def test_resume_without_a_valid_position_uses_last_shown_record(tmp_path, stored_position):
    first, second = SAMPLE_QUESTIONS
    first_state = ReviewState(
        first.id, correct=1, last_shown_at=(NOW - timedelta(days=1)).isoformat()
    )
    second_state = ReviewState(second.id, incorrect=2, last_shown_at=NOW.isoformat())
    write_json(
        tmp_path / "review.json",
        {
            "version": 2,
            "banks": {"builtin": {first.id: asdict(first_state), second.id: asdict(second_state)}},
            "positions": {"builtin": stored_position},
        },
    )

    scheduler = make_scheduler(tmp_path)
    assert scheduler.resume(SAMPLE_QUESTIONS) == (1, second.id)
    assert scheduler.states[first.id].correct == 1
    assert scheduler.states[second.id].incorrect == 2
    assert make_scheduler(tmp_path).position.question_id == second.id


def test_completed_single_question_resumes_without_recording_another_attempt(tmp_path):
    scheduler = make_scheduler(tmp_path)
    question = SAMPLE_QUESTIONS[0]
    scheduler.record(question.id, True)
    restored = make_scheduler(tmp_path)
    assert restored.resume((question,)) == (0, question.id)
    assert restored.states[question.id].attempts == 1
    assert restored.position.completed is False

"""Injectable review scoring, spacing policy, clock, RNG, and state path."""

import logging
import math
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from random import SystemRandom
from typing import Callable, Iterator, Protocol

from .models import QuizQuestion
from .paths import DATA_DIR
from .storage import read_json, write_json

logger = logging.getLogger(__name__)


@dataclass
class ReviewState:
    question_id: str
    attempts: int = 0
    correct: int = 0
    incorrect: int = 0
    streak: int = 0
    interval_days: float = 0.0
    due_at: str | None = None
    last_shown_at: str | None = None
    cooldown_until: str | None = None

    @property
    def weight(self) -> float:
        if self.attempts == 0:
            return 1.0
        return 0.8 * self.incorrect / self.attempts + 0.2 * (1.0 - min(self.correct / 5.0, 1.0))

    @classmethod
    def from_dict(cls, key: str, raw: object) -> "ReviewState":
        if not isinstance(raw, dict):
            raise ValueError("invalid review state")
        state = cls(key)
        for name in ("correct", "incorrect", "streak", "attempts"):
            value = raw.get(name, 0)
            if type(value) is not int or value < 0:
                raise ValueError("invalid counter")
            setattr(state, name, value)
        state.attempts = state.correct + state.incorrect
        state.streak = min(state.streak, state.correct)
        interval = raw.get("interval_days", 0)
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (float, int))
            or not math.isfinite(interval)
            or interval < 0
        ):
            raise ValueError("invalid interval")
        state.interval_days = float(interval)
        for name in ("due_at", "last_shown_at", "cooldown_until"):
            parsed = parse_time(raw.get(name))
            setattr(state, name, parsed.isoformat() if parsed else None)
        return state


@dataclass(frozen=True)
class StudyPosition:
    question_id: str
    completed: bool = False

    @classmethod
    def from_dict(cls, raw: object) -> "StudyPosition":
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("question_id"), str)
            or not raw["question_id"]
            or type(raw.get("completed")) is not bool
        ):
            raise ValueError("invalid study position")
        return cls(raw["question_id"], raw["completed"])


def now() -> datetime:
    return datetime.now().astimezone()


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone() if result.tzinfo is None else result
    except ValueError:
        return None


class ReviewStrategy(Protocol):
    def score(self, state: ReviewState, current: datetime) -> float: ...


@dataclass(frozen=True)
class WeightedReviewStrategy:
    due_weight: float = 0.55
    difficulty_weight: float = 0.35
    new_weight: float = 0.1

    def score(self, state: ReviewState, current: datetime) -> float:
        due, cooldown = parse_time(state.due_at), parse_time(state.cooldown_until)
        overdue = 1.0 if due is None or due <= current else 0.0
        if due and due < current:
            overdue += min((current - due).total_seconds() / 86400.0, 2.0)
        cooling = 0.12 if cooldown and cooldown > current else 1.0
        return max(
            0.05,
            (
                self.due_weight * overdue
                + self.difficulty_weight * state.weight
                + (self.new_weight if state.attempts == 0 else 0.0)
            )
            * cooling,
        )


class SpacingPolicy(Protocol):
    def update(self, state: ReviewState, correct: bool, current: datetime) -> None: ...


@dataclass(frozen=True)
class SpacedReviewPolicy:
    intervals: tuple[int, ...] = (1, 3, 7, 14, 30)
    retry_minutes: int = 5
    correct_cooldown_seconds: int = 20
    incorrect_cooldown_seconds: int = 5

    def __post_init__(self) -> None:
        if not self.intervals or any(type(day) is not int or day <= 0 for day in self.intervals):
            raise ValueError("复习间隔必须为正整数天数")
        for value in (
            self.retry_minutes,
            self.correct_cooldown_seconds,
            self.incorrect_cooldown_seconds,
        ):
            if type(value) is not int or value < 0:
                raise ValueError("复习重试和冷却时间必须为非负整数")

    def update(self, state: ReviewState, correct: bool, current: datetime) -> None:
        if correct:
            state.streak += 1
            state.interval_days = self.intervals[min(state.streak - 1, len(self.intervals) - 1)]
            due = current + timedelta(days=state.interval_days)
        else:
            state.streak = 0
            state.interval_days = 0
            due = current + timedelta(minutes=self.retry_minutes)
        state.due_at = due.isoformat()
        seconds = self.correct_cooldown_seconds if correct else self.incorrect_cooldown_seconds
        state.cooldown_until = (current + timedelta(seconds=seconds)).isoformat()


class ReviewScheduler:
    def __init__(
        self,
        path: Path | None = None,
        strategy: ReviewStrategy | None = None,
        policy: SpacingPolicy | None = None,
        clock: Callable[[], datetime] = now,
        rng=None,
        bank_id: str = "builtin",
    ) -> None:
        self.path = path or DATA_DIR / "review_state.json"
        self.strategy = strategy or WeightedReviewStrategy()
        self.policy = policy or SpacedReviewPolicy()
        self.clock = clock
        self.rng = rng if rng is not None else SystemRandom()
        self.bank_id = bank_id
        self._banks: dict[str, dict[str, ReviewState]] = {}
        self._positions: dict[str, StudyPosition] = {}
        self._defer_saves = False
        self.load()

    @property
    def states(self) -> dict[str, ReviewState]:
        return self._banks.setdefault(self.bank_id, {})

    @states.setter
    def states(self, value: dict[str, ReviewState]) -> None:
        self._banks[self.bank_id] = value

    @property
    def position(self) -> StudyPosition | None:
        return self._positions.get(self.bank_id)

    def switch_bank(self, bank_id: str) -> None:
        if not isinstance(bank_id, str) or not bank_id:
            raise ValueError("题库标识不能为空")
        self.bank_id = bank_id

    def load(self) -> None:
        self._banks = {}
        self._positions = {}
        try:
            raw = read_json(self.path)
            if (
                not isinstance(raw, dict)
                or raw.get("version") != 2
                or not isinstance(raw.get("banks"), dict)
            ):
                raise ValueError("invalid review file")
            for bank_id, entries in raw["banks"].items():
                if not bank_id or not isinstance(entries, dict):
                    logger.warning("invalid review bank ignored: %s", bank_id)
                    continue
                bank = {}
                for key, value in entries.items():
                    try:
                        bank[key] = ReviewState.from_dict(key, value)
                    except (ValueError, TypeError):
                        logger.warning("invalid review entry ignored: %s/%s", bank_id, key)
                self._banks[bank_id] = bank
            positions = raw.get("positions", {})
            if isinstance(positions, dict):
                for bank_id, value in positions.items():
                    try:
                        if not bank_id:
                            raise ValueError("empty bank id")
                        self._positions[bank_id] = StudyPosition.from_dict(value)
                    except ValueError:
                        logger.warning("invalid study position ignored: %s", bank_id)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            logger.warning("review state unavailable; using defaults", exc_info=True)

    def save(self) -> None:
        if self._defer_saves:
            return
        write_json(
            self.path,
            {
                "version": 2,
                "banks": {
                    bank_id: {key: asdict(state) for key, state in bank.items()}
                    for bank_id, bank in self._banks.items()
                },
                "positions": {
                    bank_id: asdict(position) for bank_id, position in self._positions.items()
                },
            },
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit a bank transition once, keeping the original state on failure."""
        if self._defer_saves:
            raise ValueError("复习保存事务不能嵌套")
        previous_bank = self.bank_id
        previous_banks = deepcopy(self._banks)
        previous_positions = dict(self._positions)
        self._defer_saves = True
        try:
            yield
            self._defer_saves = False
            self.save()
        except BaseException:
            self.bank_id = previous_bank
            self._banks = previous_banks
            self._positions = previous_positions
            raise
        finally:
            self._defer_saves = False

    @staticmethod
    def question_id(question: QuizQuestion, index: int = 0) -> str:
        return question.id

    def sync_questions(self, questions: tuple[QuizQuestion, ...]) -> None:
        changed = False
        previous = dict(self.states)
        for question in questions:
            if question.id not in self.states:
                self.states[question.id] = ReviewState(question.id)
                changed = True
        if changed:
            try:
                self.save()
            except OSError:
                self.states = previous
                raise

    def mark_shown(self, question_id: str) -> None:
        previous = self.states.get(question_id)
        previous_position = self.position
        state = ReviewState(**asdict(previous)) if previous else ReviewState(question_id)
        current = self.clock()
        state.last_shown_at = current.isoformat()
        state.cooldown_until = (current + timedelta(seconds=20)).isoformat()
        self.states[question_id] = state
        self._positions[self.bank_id] = StudyPosition(question_id)
        try:
            self.save()
        except OSError:
            if previous is None:
                self.states.pop(question_id, None)
            else:
                self.states[question_id] = previous
            self._restore_position(previous_position)
            raise

    def _restore_position(self, position: StudyPosition | None) -> None:
        if position is None:
            self._positions.pop(self.bank_id, None)
        else:
            self._positions[self.bank_id] = position

    def resume(self, questions: tuple[QuizQuestion, ...]) -> tuple[int, str]:
        """Resume an unfinished question, or recommend the next after a completed one."""
        if not questions:
            raise ValueError("不能恢复空题库")
        self.sync_questions(questions)
        indices = {question.id: index for index, question in enumerate(questions)}
        position = self.position
        if position is not None:
            if position.completed or position.question_id not in indices:
                return self.choose(questions, position.question_id)
            index = indices[position.question_id]
        else:
            shown = [
                (timestamp, question.id)
                for question in questions
                if (timestamp := parse_time(self.states[question.id].last_shown_at)) is not None
            ]
            index = indices[max(shown)[1]] if shown else 0
        identifier = questions[index].id
        self.mark_shown(identifier)
        return index, identifier

    def choose(
        self, questions: tuple[QuizQuestion, ...], last_id: str | None = None
    ) -> tuple[int, str]:
        if not questions:
            raise ValueError("不能从空题库选题")
        self.sync_questions(questions)
        current = self.clock()
        candidates = [
            (index, question.id)
            for index, question in enumerate(questions)
            if question.id != last_id or len(questions) == 1
        ]
        if not candidates:
            raise ValueError("没有可用题目")
        scores = [
            self.strategy.score(self.states[question_id], current) for _, question_id in candidates
        ]
        if any(
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or score <= 0
            for score in scores
        ):
            raise ValueError("复习策略必须返回有限的正权重")
        target = self.rng.random() * sum(scores)
        chosen = candidates[-1]
        for candidate, score in zip(candidates, scores):
            target -= score
            if target <= 0:
                chosen = candidate
                break
        self.mark_shown(chosen[1])
        return chosen

    def record(self, question_id: str, correct: bool) -> None:
        previous = self.states.get(question_id, ReviewState(question_id))
        previous_position = self.position
        state = ReviewState(**asdict(previous))
        state.attempts += 1
        state.correct += int(correct)
        state.incorrect += int(not correct)
        self.policy.update(state, correct, self.clock())
        self.states[question_id] = state
        self._positions[self.bank_id] = StudyPosition(question_id, completed=correct)
        try:
            self.save()
        except (OSError, ValueError):
            self.states[question_id] = previous
            self._restore_position(previous_position)
            raise

"""Coordinates a pure quiz session with injected review and action services."""

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from .extensions import ActionContext, ActionRegistry
from .models import QuizQuestion
from .scheduler import ReviewScheduler
from .session import QuizSession

logger = logging.getLogger(__name__)


class StudyController(QObject):
    changed = Signal()
    question_changed = Signal()
    error = Signal(str)

    def __init__(
        self,
        session: QuizSession,
        scheduler: ReviewScheduler,
        actions: ActionRegistry,
        action_context: ActionContext,
        feedback_delay_ms: int = 650,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.scheduler = scheduler
        self.actions = actions
        self.action_context = action_context
        self.next_question_timer = QTimer(self)
        self.next_question_timer.setSingleShot(True)
        self.next_question_timer.setInterval(feedback_delay_ms)
        self.next_question_timer.timeout.connect(self.next_question)
        index, _ = self.scheduler.resume(self.session.questions)
        self.session.load(index)

    def load_questions(
        self, questions: tuple[QuizQuestion, ...], *, initial_index: int | None = None
    ) -> None:
        self.session.validate_questions(questions)
        if initial_index is None:
            initial_index, _ = self.scheduler.resume(questions)
        self.next_question_timer.stop()
        self.session.set_questions(questions)
        self.session.load(initial_index)
        self._question_loaded()

    def _question_loaded(self) -> None:
        self.question_changed.emit()
        self.changed.emit()

    def select_option(self, option_id: str) -> None:
        if self.session.select(option_id):
            if (
                self.session.rules.get(self.session.question.mode).auto_submit
                and self.session.selected
            ):
                self.confirm_answer()
            self.changed.emit()

    def confirm_answer(self) -> None:
        submission = self.session.submit()
        if submission is None:
            return
        try:
            self.scheduler.record(submission.question_id, submission.correct)
        except (OSError, ValueError) as error:
            self.session.cancel_submission()
            self._report("无法保存答题记录，请重试", error)
        else:
            logger.info("answer question=%s correct=%s", submission.question_id, submission.correct)
            if submission.correct:
                self.next_question_timer.start()
        self.changed.emit()

    def next_question(self) -> None:
        self.next_question_timer.stop()
        try:
            index, _ = self.scheduler.choose(self.session.questions, self.session.question.id)
        except (OSError, ValueError) as error:
            self._report("无法选择下一题", error)
            return
        self.session.load(index)
        self._question_loaded()

    def navigate_question(self, direction: str) -> None:
        if direction not in {"previous", "next"}:
            return
        self.next_question_timer.stop()
        index = (self.session.index + (-1 if direction == "previous" else 1)) % len(
            self.session.questions
        )
        try:
            self.scheduler.mark_shown(self.session.questions[index].id)
        except (OSError, ValueError) as error:
            self._report("无法保存学习位置，请重试", error)
            return
        self.session.load(index)
        self._question_loaded()

    def run_extension(self) -> None:
        action = self.session.question.extension
        if action is None:
            return
        try:
            self.actions.run(action, self.action_context)
        except Exception as error:
            self._report("扩展动作执行失败", error)

    def _report(self, message: str, error: Exception) -> None:
        logger.exception("%s: %s", message, error)
        self.error.emit(f"{message}：{error}")

    def shutdown(self) -> None:
        self.next_question_timer.stop()

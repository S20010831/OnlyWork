"""The composition point for optional application extensions."""

from dataclasses import dataclass, field

from .answers import AnswerRules, default_answer_rules
from .extensions import ActionRegistry, default_actions
from .questions import QuestionImporters, default_importers
from .scheduler import ReviewStrategy, SpacedReviewPolicy, SpacingPolicy, WeightedReviewStrategy


@dataclass
class AppServices:
    answers: AnswerRules = field(default_factory=default_answer_rules)
    actions: ActionRegistry = field(default_factory=default_actions)
    importers: QuestionImporters = field(default_factory=default_importers)
    review_strategy: ReviewStrategy = field(default_factory=WeightedReviewStrategy)
    spacing_policy: SpacingPolicy = field(default_factory=SpacedReviewPolicy)

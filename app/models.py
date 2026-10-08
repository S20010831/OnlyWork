"""UI-independent question models; IDs survive row and option reordering."""

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256


class QuestionFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ImportIssue:
    location: str
    message: str


class ImportValidationError(QuestionFormatError):
    def __init__(
        self, issues: tuple[ImportIssue, ...], valid_questions: tuple["QuizQuestion", ...] = ()
    ) -> None:
        self.issues = issues
        self.valid_questions = valid_questions
        super().__init__("\n".join(f"{issue.location}：{issue.message}" for issue in issues))


@dataclass(frozen=True)
class Option:
    id: str
    text: str


@dataclass(frozen=True)
class ExtensionAction:
    type: str
    value: str


def validate_options(options: tuple[Option, ...]) -> None:
    if any(not isinstance(option, Option) for option in options):
        raise QuestionFormatError("选项必须是 Option 对象")
    if not 3 <= len(options) <= 6:
        raise QuestionFormatError("选项数量必须为 3～6 个")
    ids = [option.id for option in options]
    if any(not isinstance(value, str) or not re.fullmatch(r"[A-Z]", value) for value in ids):
        raise QuestionFormatError("选项编号必须是 A～Z 的单个字母")
    if len(set(ids)) != len(ids):
        raise QuestionFormatError("选项编号不能重复")
    if any(not isinstance(option.text, str) or not option.text.strip() for option in options):
        raise QuestionFormatError("选项内容不能为空")


@dataclass(frozen=True)
class QuizQuestion:
    prompt: str
    subtitle: str
    options: tuple[Option, ...]
    correct_ids: frozenset[str]
    mode: str = "single"
    extension: ExtensionAction | None = None
    id: str = field(default="")
    source_row: int = field(default=0, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise QuestionFormatError("题目不能为空")
        if not isinstance(self.subtitle, str):
            raise QuestionFormatError("副标题必须是文本")
        try:
            object.__setattr__(self, "options", tuple(self.options))
            object.__setattr__(self, "correct_ids", frozenset(self.correct_ids))
        except TypeError as error:
            raise QuestionFormatError("选项和正确答案必须是集合") from error
        validate_options(self.options)
        ids = {option.id for option in self.options}
        if not self.correct_ids or not self.correct_ids <= set(ids):
            raise QuestionFormatError("正确选项不存在或为空")
        if not isinstance(self.mode, str) or not self.mode.strip():
            raise QuestionFormatError("题型不能为空")
        if self.extension is not None:
            if not isinstance(self.extension, ExtensionAction):
                raise QuestionFormatError("扩展必须是 ExtensionAction 对象")
            if (
                not isinstance(self.extension.type, str)
                or not isinstance(self.extension.value, str)
                or not self.extension.type.strip()
                or not self.extension.value.strip()
            ):
                raise QuestionFormatError("扩展动作类型和内容必须是非空文本")
        if not isinstance(self.id, str):
            raise QuestionFormatError("题目 ID 必须是文本")
        object.__setattr__(self, "id", self.id.strip())
        if not self.id:
            content = [
                self.prompt.strip(),
                self.mode,
                sorted((option.id, option.text.strip()) for option in self.options),
                sorted(self.correct_ids),
            ]
            digest = sha256(json.dumps(content, ensure_ascii=False).encode("utf-8")).hexdigest()
            object.__setattr__(self, "id", "q-" + digest)

import json

import pytest
from openpyxl import Workbook

from app.models import ExtensionAction, QuestionFormatError, QuizQuestion
from app.questions import (
    SAMPLE_QUESTIONS,
    default_importers,
    load_questions_from_json,
    load_questions_from_xlsx,
    parse_extension,
    parse_question_text,
    question_to_dict,
)


def make_workbook(tmp_path, rows):
    path = tmp_path / "questions.xlsx"
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    workbook.save(path)
    workbook.close()
    return path


def test_excel_named_columns_blank_rows_and_optional_fields(tmp_path):
    path = make_workbook(
        tmp_path,
        [
            ["扩展", "正确选项", "题目", "A", "B", "C", "ID", "D", "E", "F"],
            ["info:解释", "A|C", "题目一\n多选", "甲", "乙", "丙", 1, None, None, None],
            [None] * 10,
            [None, "F", "题目二", "a", "b", "c", None, "d", "e", "f"],
        ],
    )
    questions = load_questions_from_xlsx(path)
    assert questions[0].mode == "multiple"
    assert questions[0].id == "1"
    assert questions[0].subtitle == "多选"
    assert questions[0].extension == ExtensionAction("info", "解释")
    assert len(questions[1].options) == 6
    path.unlink()


def test_excel_serial_ids_inline_hints_and_automatic_modes(tmp_path):
    path = make_workbook(
        tmp_path,
        [
            ["ID", "题目", "A", "B", "C", "正确选项", "扩展"],
            [1, "abandon\n/əˈbændən/\nv.", "甲", "乙", "丙", "A", None],
            [2, "Which are mammals?", "鲸鱼", "蝙蝠", "鳄鱼", "A|B", None],
        ],
    )
    first, second = load_questions_from_xlsx(path)
    assert (first.id, first.prompt, first.subtitle, first.mode) == (
        "1",
        "abandon",
        "/əˈbændən/\nv.",
        "single",
    )
    assert (second.id, second.subtitle, second.mode) == ("2", "", "multiple")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_question_text_normalizes_line_endings(newline):
    assert parse_question_text(f"abandon{newline}音标{newline}词性") == ("abandon", "音标\n词性")


@pytest.mark.parametrize("column", ["选项", "副标题", "题型"])
def test_removed_excel_columns_are_rejected(tmp_path, column):
    path = make_workbook(
        tmp_path,
        [
            ["题目", "A", "B", "C", "正确选项", column],
            ["word", "甲", "乙", "丙", "A", "old-format"],
        ],
    )
    with pytest.raises(QuestionFormatError, match="不支持的题库列"):
        load_questions_from_xlsx(path)


def test_inline_hint_does_not_reset_generated_identity(tmp_path):
    path = make_workbook(
        tmp_path,
        [
            ["题目", "A", "B", "C", "正确选项"],
            ["abandon\n新提示", "放弃；遗弃", "记住；回忆", "逃跑；逃脱", "A"],
        ],
    )
    assert load_questions_from_xlsx(path)[0].id == SAMPLE_QUESTIONS[0].id


@pytest.mark.parametrize(
    "rows,match",
    [
        ([["题目"], ["题目一"]], "缺少必需列"),
        ([["题目", "A", "B", "C", "正确选项"], ["q", "a", "b", None, "A"]], "第 2 行"),
        ([["题目", "A", "B", "C", "正确选项"], ["q", "a", "b", "c", "D"]], "不存在"),
        ([["题目", "A", "B", "C", "正确选项"], [None, "a", "b", "c", "A"]], "题目"),
        ([["题目", "A", "B", "C", "正确选项"]], "没有题目"),
    ],
)
def test_excel_format_errors_are_user_facing(tmp_path, rows, match):
    with pytest.raises(QuestionFormatError, match=match):
        load_questions_from_xlsx(make_workbook(tmp_path, rows))


def test_corrupt_excel_is_format_error(tmp_path):
    path = tmp_path / "bad.xlsx"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(QuestionFormatError):
        load_questions_from_xlsx(path)


def test_import_lists_all_errors_and_rows(tmp_path):
    from app.models import ImportValidationError

    path = make_workbook(
        tmp_path,
        [
            ["ID", "题目", "A", "B", "C", "正确选项", "扩展"],
            [1, None, "a", "b", None, "D", "invalid"],
            [1, "other", "a", "b", "c", "A", None],
            [2, "last", "a", "b", "c", "F", None],
        ],
    )
    with pytest.raises(ImportValidationError) as caught:
        load_questions_from_xlsx(path)
    assert len(caught.value.issues) == 6
    assert {issue.location for issue in caught.value.issues} == {"第 2 行", "第 3 行", "第 4 行"}
    assert "首次出现在第 2 行" in str(caught.value)


@pytest.mark.parametrize("identifier", [0, -1, 1.5, True, "bad"])
def test_excel_serial_id_must_be_a_positive_integer(tmp_path, identifier):
    path = make_workbook(
        tmp_path,
        [
            ["ID", "题目", "A", "B", "C", "正确选项"],
            [identifier, "q", "a", "b", "c", "A"],
        ],
    )
    with pytest.raises(QuestionFormatError, match="正整数序号"):
        load_questions_from_xlsx(path)


def test_identity_survives_row_and_option_reordering():
    first = SAMPLE_QUESTIONS[0]
    reordered = QuizQuestion(
        first.prompt, first.subtitle, tuple(reversed(first.options)), first.correct_ids, first.mode
    )
    assert first.id == reordered.id
    changed = QuizQuestion(first.prompt, "", first.options, frozenset({"B"}))
    assert changed.id != first.id


def test_json_roundtrip_and_reject_duplicate_ids(tmp_path):
    path = tmp_path / "bank.json"
    values = [question_to_dict(question) for question in SAMPLE_QUESTIONS]
    path.write_text(json.dumps({"version": 1, "questions": values}), encoding="utf-8")
    assert load_questions_from_json(path) == SAMPLE_QUESTIONS
    path.write_text(json.dumps([values[0], values[0]]), encoding="utf-8")
    with pytest.raises(QuestionFormatError, match="重复"):
        load_questions_from_json(path)


@pytest.mark.parametrize(
    "value", [{}, {"version": 2, "questions": []}, ["bad"], {"questions": "bad"}]
)
def test_invalid_json_shape(tmp_path, value):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(QuestionFormatError):
        load_questions_from_json(path)


def test_json_hints_use_prompt_newlines(tmp_path):
    value = question_to_dict(SAMPLE_QUESTIONS[0])
    assert "subtitle" not in value
    assert value["prompt"] == "abandon\n/əˈbændən/  v."
    value["subtitle"] = "old-format"
    path = tmp_path / "old-format.json"
    path.write_text(json.dumps([value]), encoding="utf-8")
    with pytest.raises(QuestionFormatError, match="不支持的题目字段"):
        load_questions_from_json(path)


def test_extension_preserves_colons_and_can_be_custom():
    assert (
        parse_extension("url:https://example.com:443/path").value == "https://example.com:443/path"
    )
    assert parse_extension("lookup:word") == ExtensionAction("lookup", "word")
    assert parse_extension(None) is None
    with pytest.raises(QuestionFormatError):
        parse_extension("info:")


def test_custom_importer_is_used(tmp_path):
    importers = default_importers()
    importers.register(".custom", lambda path: SAMPLE_QUESTIONS)
    assert importers.load(tmp_path / "bank.custom") == SAMPLE_QUESTIONS
    assert "*.custom" in importers.file_filter

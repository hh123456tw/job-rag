"""票 22：history 驗證與截斷、追問補全規則（正反例）。規則只寫在 job_rag/memory.py。"""
import json

import pytest

from job_rag.memory import MAX_ANSWER, HistoryError, clean_history, expand
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

PREV = [{"q": "甲科技有哪些職缺？", "a": "徵後端工程師 [1]"}]


def ex(q, hist=PREV):
    return expand(q, hist, corpus=MINI)


# ---- 補全規則：正例 ----
@pytest.mark.parametrize("q", ["那薪水呢？", "要出差嗎？", "它的資本額是多少？", "那需要作品集嗎？"])
def test_short_question_without_company_or_topic_gets_previous_question_in_front(q):
    assert ex(q) == f"甲科技有哪些職缺？ {q}"


def test_only_the_last_user_question_is_prepended_not_the_answer():
    hist = [{"q": "乙資訊做什麼？", "a": "物流排程"}, {"q": "甲科技有哪些職缺？", "a": "答案文字"}]
    out = ex("那薪水呢？", hist)
    assert out == "甲科技有哪些職缺？ 那薪水呢？" and "答案文字" not in out


# ---- 補全規則：反例 ----
def test_first_turn_has_nothing_to_prepend():
    assert ex("那薪水呢？", []) == "那薪水呢？"


@pytest.mark.parametrize("q", ["乙資訊的薪水呢？", "甲科技呢？"])
def test_question_naming_a_company_is_left_alone(q):
    assert ex(q) == q


@pytest.mark.parametrize("q", ["有哪些職缺？", "用什麼技術？", "最近有什麼新聞？", "有 AI 產品嗎？"])
def test_question_with_its_own_topic_word_is_left_alone(q):
    assert ex(q) == q


def test_long_question_is_left_alone():
    q = "那他們的薪水範圍大概是多少，有沒有分資深跟資淺的差別？"
    assert len(q) > 12 and ex(q) == q


def test_twelve_chars_is_short_thirteen_is_not():
    assert ex("一" * 12).startswith("甲科技") and ex("一" * 13) == "一" * 13


def test_ai_topic_word_is_matched_as_a_word_not_inside_other_letters():
    assert ex("Rain 呢？").startswith("甲科技")  # 「Rain」含 ai，但不是 AI 這個詞
    assert ex("有 AI 嗎？") == "有 AI 嗎？"


# ---- history 驗證 ----
def raw(x):
    return json.dumps(x, ensure_ascii=False)


def test_empty_or_missing_history_is_empty_list():
    assert clean_history(None) == [] and clean_history("") == [] and clean_history("[]") == []


def test_keeps_only_the_last_two_turns():
    turns = [{"q": f"問{i}", "a": f"答{i}"} for i in range(5)]
    assert clean_history(raw(turns)) == turns[-2:]


def test_answers_are_cut_to_300_chars_and_questions_to_200():
    out = clean_history(raw([{"q": "題" * 500, "a": "答" * 1000}]))
    assert len(out[0]["a"]) == MAX_ANSWER == 300 and len(out[0]["q"]) == 200


def test_whitespace_and_newlines_are_flattened():
    assert clean_history(raw([{"q": "甲\n\n乙", "a": "丙\r\n  丁"}])) == [{"q": "甲 乙", "a": "丙 丁"}]


@pytest.mark.parametrize("bad", [
    "not json", raw({"q": "x", "a": "y"}), raw("字串"), raw([1]), raw([{"q": "x"}]), raw([{"q": 1, "a": "y"}]),
    raw([{"q": "x", "a": None}]), raw([["x", "y"]]), "x" * 5000,
    raw([{"q": "x", "a": "y"}] * 3 + ["壞"]),  # 前面的項目也要檢查，不是只看最後兩則
])
def test_malformed_or_oversized_history_is_rejected(bad):
    with pytest.raises(HistoryError):
        clean_history(bad)


def test_turns_with_empty_question_are_dropped():
    assert clean_history(raw([{"q": "  ", "a": "y"}, {"q": "好", "a": "z"}])) == [{"q": "好", "a": "z"}]

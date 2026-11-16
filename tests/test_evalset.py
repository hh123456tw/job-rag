"""評估題資料檔的檢查：佐證引文真的在金標標題之下；不可回答題的關鍵字真的搜不到。"""
from pathlib import Path

from job_rag.evalset import to_markdown, verify

MINI = Path(__file__).parent / "fixtures" / "mini"
PEND = "待使用者確認"


def A(id, gold, private=False, **kw):
    return {"id": id, "question": "題", "type": "單一公司", "answerable": True, "private": private,
            "gold": gold, "status": PEND} | kw


def U(id, keywords, **kw):
    return {"id": id, "question": "題", "type": "不可回答", "answerable": False, "private": False,
            "gold": [], "absence_keywords": keywords, "status": PEND} | kw


def g(file, heading, quote):
    return {"file": file, "heading": heading, "quote": quote}


def test_good_answerable_and_unanswerable_pass():
    qs = [A("a", [g("01_甲科技.md", "1. 基本資料", "鯨魚追蹤軟體")]), U("u", ["量子麵包", "xyzzy"])]
    assert verify(qs, MINI) == []


def test_quote_under_subheading_counts_as_under_gold_heading():
    qs = [A("a", [g("01_甲科技.md", "4. 職缺（後端）", "月薪四萬到六萬")])]  # 在 4.1 子標題內
    assert verify(qs, MINI) == []


def test_quote_in_other_heading_is_rejected():
    # 負向：引文存在於檔案，但不在金標標題之下
    qs = [A("a", [g("01_甲科技.md", "2. 業務與財務", "鯨魚追蹤軟體")])]
    assert any("a" in p and "引文" in p for p in verify(qs, MINI))


def test_missing_file_or_heading_is_reported():
    assert verify([A("a", [g("nope.md", "x", "y")])], MINI)
    assert verify([A("a", [g("01_甲科技.md", "9. 不存在", "y")])], MINI)


def test_similar_heading_name_is_not_the_gold_heading():
    # 「職缺」不是「職缺風險」
    qs = [A("a", [g("01_甲科技.md", "職缺", "河馬密語")])]
    assert verify(qs, MINI)


def test_answerable_without_quote_is_rejected():
    assert verify([A("a", [{"file": "01_甲科技.md", "heading": "1. 基本資料"}])], MINI)
    assert verify([A("a", [])], MINI)


def test_unanswerable_keyword_found_in_corpus_is_rejected():
    assert any("鯨魚" in p for p in verify([U("u", ["鯨魚", "量子麵包"])], MINI))


def test_unanswerable_keyword_found_in_subfolder_is_rejected():
    assert verify([U("u", ["貓頭鷹"])], MINI)  # 104/A_甲科技.md


def test_unanswerable_without_keywords_is_rejected():
    assert verify([U("u", [])], MINI)


def test_private_flag_must_match_gold_classification():
    pub_as_private = A("a", [g("01_甲科技.md", "1. 基本資料", "鯨魚")], private=True)
    priv_as_public = A("b", [g("02_乙資訊.md", "7. 工作評價", "刺蝟密語")], private=False)
    assert verify([pub_as_private], MINI) and verify([priv_as_public], MINI)
    assert verify([A("c", [g("02_乙資訊.md", "7. 工作評價", "刺蝟密語")], private=True)], MINI) == []


def test_agent_cannot_mark_a_question_confirmed():
    qs = [A("a", [g("01_甲科技.md", "1. 基本資料", "鯨魚")], status="已確認")]
    assert any("核對狀態" in p for p in verify(qs, MINI))


def test_duplicate_ids_rejected():
    ok = A("a", [g("01_甲科技.md", "1. 基本資料", "鯨魚")])
    assert verify([ok, dict(ok)], MINI)


def test_markdown_table_has_required_columns_and_pending_status():
    qs = [A("a", [g("01_甲科技.md", "1. 基本資料", "鯨魚追蹤軟體")]), U("u", ["量子麵包"])]
    md = to_markdown(qs)
    for col in ("題目", "類型", "金標檔案與標題", "佐證", "核對狀態"):
        assert col in md
    assert md.count(PEND) == 2 and "量子麵包" in md and "鯨魚追蹤軟體" in md


# ---- 真正的 eval/questions.json ----
import json
import os
from collections import Counter

import pytest

REAL = Path(__file__).parent.parent / "eval" / "questions.json"


def _real():
    return json.loads(REAL.read_text(encoding="utf-8"))["questions"]


def test_real_question_set_composition():
    qs = _real()
    assert len(qs) == 30
    assert sum(q["answerable"] for q in qs) == 25
    c = Counter(q["type"] for q in qs)
    assert c["不可回答"] == 5 and all(c[t] > 0 for t in ("跨公司", "單一公司", "職缺", "面試與評價"))
    assert all(q["private"] for q in qs if q["type"] == "面試與評價")
    assert all(not q["private"] for q in qs if q["type"] != "面試與評價")
    assert all(q["status"] == PEND for q in qs)  # 只有使用者能改成已確認


@pytest.mark.skipif(not os.environ.get("JOB_RAG_CORPUS"), reason="需要完整語料")
def test_real_question_set_verifies_against_real_corpus():
    assert verify(_real()) == []

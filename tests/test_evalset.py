"""評估題資料檔的檢查：佐證引文真的在金標標題之下；不可回答題的關鍵字真的搜不到。"""
from pathlib import Path

from job_rag.evalset import to_markdown, type_summary, verify

MINI = Path(__file__).parent / "fixtures" / "mini"
PEND = "待使用者確認"


def A(id, gold, **kw):
    return {"id": id, "question": "題", "type": "單一公司", "answerable": True,
            "gold": gold, "status": PEND} | kw


def U(id, keywords, **kw):
    return {"id": id, "question": "題", "type": "不可回答", "answerable": False,
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


def test_gold_in_excluded_section_is_rejected():
    # 排除段落（工作評價）不能當金標；公開段落可以
    bad = A("b", [g("02_乙資訊.md", "7. 工作評價", "刺蝟密語")])
    assert any("排除段落" in p for p in verify([bad], MINI))
    assert verify([A("a", [g("01_甲科技.md", "1. 基本資料", "鯨魚")])], MINI) == []


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
    assert "私人" not in md and "查詢模式" not in md


def test_type_summary_counts_by_type():
    qs = [A("a", [], type="跨公司"), A("b", [], type="跨公司"), A("c", [], type="職缺"), U("u", ["x"])]
    assert type_summary(qs) == "跨公司 2、職缺 1、不可回答 1"


# ---- 完整題組 eval/questions.json（私人 repo 才有）----
import json
import os
from collections import Counter

import pytest

# 完整題組（30 題）不在公開版裡：設 JOB_RAG_REAL_QUESTIONS=<完整 questions.json> 才跑這一節
REAL_PATH = os.environ.get("JOB_RAG_REAL_QUESTIONS")
needs_real = pytest.mark.skipif(not REAL_PATH, reason="需要完整題組（JOB_RAG_REAL_QUESTIONS）")


def _real():
    return json.loads(Path(REAL_PATH).read_text(encoding="utf-8"))["questions"]


@needs_real
def test_real_question_set_composition():
    qs = _real()
    assert len(qs) == 30
    assert sum(q["answerable"] for q in qs) == 25
    c = Counter(q["type"] for q in qs)
    assert c["不可回答"] == 5 and all(c[t] > 0 for t in ("跨公司", "單一公司", "職缺"))
    assert c["跨公司"] <= 3  # 答案散在多處的題少放，金標容易漏列
    assert set(c) == {"跨公司", "單一公司", "職缺", "不可回答"}
    assert all(q["status"] == PEND for q in qs)  # 只有使用者能改成已確認
    assert all("private" not in q for q in qs)


@needs_real
def test_no_interview_or_review_questions_remain():
    # 面試／評價題（排除段落）已移除：題號 i** 不存在，金標不指向「面試」「評價」標題
    qs = _real()
    assert not any(q["id"].startswith("i") for q in qs)
    heads = [g["heading"] for q in qs for g in q["gold"]]
    assert not any(w in h for h in heads for w in ("面試", "評價"))


@needs_real
@pytest.mark.skipif(not os.environ.get("JOB_RAG_REAL_CORPUS"), reason="需要完整語料（JOB_RAG_REAL_CORPUS）")
def test_real_question_set_verifies_against_real_corpus():
    assert verify(_real(), os.environ["JOB_RAG_REAL_CORPUS"]) == []


def test_gold_in_an_excluded_company_is_rejected(tmp_path, monkeypatch):
    # 票 23：公司在移出名單內，它的段落不在索引裡；金標指到那裡要被擋下（引文雖然真的在原檔）
    from job_rag import retrieval
    (tmp_path / "01_甲科技.md").write_text("# 甲\n## 1. 基本資料\n甲科技做鯨魚追蹤。\n", encoding="utf-8")
    (tmp_path / "02_乙資訊.md").write_text("# 乙\n## 1. 基本資料\n乙資訊做資安。\n", encoding="utf-8")
    qs = [A("a", [g("02_乙資訊.md", "1. 基本資料", "乙資訊做資安")])]
    assert verify(qs, tmp_path) == []
    monkeypatch.setattr(retrieval, "EXCLUDED_COMPANIES", frozenset({"乙資訊"}))
    retrieval._parse.cache_clear()
    try:
        assert any("不在索引內" in p for p in verify(qs, tmp_path))
    finally:
        retrieval._parse.cache_clear()

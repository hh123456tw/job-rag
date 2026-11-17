"""獨立測試題 100 題（eval/questions_heldout.json；2026-11-17 取代舊 40 題）的組成與金標檢查。
題檔只在私人 repo；沒有題檔就整檔跳過。核對真語料需設 JOB_RAG_REAL_CORPUS。"""
import json
import os
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
QFILE = ROOT / "eval" / "questions_heldout.json"
pytestmark = pytest.mark.skipif(not QFILE.is_file(), reason="需要私人 repo 的獨立測試題（eval/questions_heldout.json）")
COMPANIES = ["台灣大哥大", "聯合報", "叡揚資訊", "神通資訊", "藍新資訊", "凱基證券", "華電聯網", "中華網龍",
             "宏碁雲架構", "典凡科技", "遠振資訊", "艾普特", "數據立"]
LIVE = COMPANIES[:8]


def _qs():
    return json.loads(QFILE.read_text(encoding="utf-8"))["questions"]


def test_composition_100_questions_by_type_with_ids_and_split():
    qs = _qs()
    assert len(qs) == 100 and len({q["id"] for q in qs}) == 100
    assert [q["id"] for q in qs] == [f"g{i:03d}" for i in range(1, 101)]
    assert Counter(q["type"] for q in qs) == {"單一公司": 56, "職缺": 16, "跨公司": 10, "不可回答": 18}
    assert sum(q["answerable"] for q in qs) == 82
    assert all(q["split"] == "gen100" and q["status"].startswith("待使用者確認") for q in qs)  # 只有使用者能改成已確認
    assert all("private" not in q for q in qs)


def test_each_live_company_has_single_company_and_job_list_questions():
    qs = _qs()
    for c in LIVE:
        assert sum(q["type"] == "單一公司" and q["company"] == c for q in qs) == 7, c
        assert sum(q["type"] == "職缺" and q["company"] == c for q in qs) == 2, c


def test_company_page_questions_do_not_repeat_company_name_and_use_only_live_companies():
    short = [q for q in _qs() if q.get("company")]
    assert {q["company"] for q in short} <= set(LIVE)  # 公司頁只有現場 8 家有


def test_cross_questions_use_keywords_without_single_company_and_do_not_name_a_company():
    cross = [q for q in _qs() if q["type"] == "跨公司"]
    assert len(cross) == 10
    for q in cross:
        assert q["answerable"] and q["keywords"] and "company" not in q
        assert not any(c in q["question"] for c in COMPANIES)


def test_unanswerable_have_absence_keywords_no_gold_and_a_few_traps():
    un = [q for q in _qs() if not q["answerable"]]
    assert len(un) == 18 and all(q["gold"] == [] and q["absence_keywords"] for q in un)
    assert sum(bool(q.get("trap")) for q in un) >= 3


def test_every_answerable_non_cross_gold_has_file_heading_and_quote():
    for q in _qs():
        if q["answerable"] and q["type"] != "跨公司":
            assert q["gold"] and all(g["file"] and g["heading"] and g["quote"] for g in q["gold"]), q["id"]


def test_questions_do_not_leak_private_section_words():
    blob = json.dumps(_qs(), ensure_ascii=False)
    assert not any(w in blob for w in ("面試", "評價", "作戰", "媒合", "private"))


# ---- 真語料：金標只落在公開段落、引文真的在標題底下、沒答案題的關鍵字在整份語料出現 0 次（題檔 absence_reviewed 列出的例外除外）----
CORPUS = os.environ.get("JOB_RAG_REAL_CORPUS")
needs_corpus = pytest.mark.skipif(not CORPUS, reason="需要完整語料（JOB_RAG_REAL_CORPUS）")


@needs_corpus
def test_evalset_verify_passes_on_the_real_corpus():
    from job_rag.evalset import verify
    assert verify(_qs(), CORPUS) == []


@needs_corpus
def test_unanswerable_keywords_appear_zero_times_in_the_whole_corpus_including_excluded():
    text = "".join(re.sub(r"\s+", "", p.read_text(encoding="utf-8")).lower() for p in Path(CORPUS).rglob("*.md"))
    for q in _qs():
        if not q["answerable"]:
            for kw in q["absence_keywords"]:
                if kw in q.get("absence_reviewed", {}):  # 新語料命中、人工讀過確認沒回答題目（理由寫在題檔）
                    continue
                assert re.sub(r"\s+", "", kw).lower() not in text, (q["id"], kw)


@needs_corpus
def test_cross_keywords_occur_in_a_public_segment_of_a_live_company():
    from job_rag import retrieval
    segs = [s for s in retrieval._public(retrieval._root(CORPUS, "demo")) if s["company"] in LIVE]
    for q in _qs():
        if q["type"] == "跨公司":
            assert any(k.lower() in s["text"].lower() for k in q["keywords"] for s in segs), q["id"]

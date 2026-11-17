"""票 39：獨立測試題 40 題（eval/questions_heldout.json）的組成與金標檢查。
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


def test_composition_26_answerable_14_unanswerable_with_ids_and_split():
    qs = _qs()
    assert len(qs) == 40 and len({q["id"] for q in qs}) == 40
    assert [q["id"] for q in qs] == [f"h{i:02d}" for i in range(1, 41)]
    assert sum(q["answerable"] for q in qs) == 26  # h40 於 2026-11-17 因新語料已含答案改標為可回答
    assert all(q["split"] == "heldout" and q["status"].startswith("待使用者確認") for q in qs)  # 只有使用者能改成已確認
    assert all("private" not in q for q in qs)


def test_all_13_companies_appear_in_answerable_questions():
    qs = [q for q in _qs() if q["answerable"]]
    seen = {c for q in qs for c in COMPANIES if c == q.get("company") or c in q["question"]}
    assert seen == set(COMPANIES)


def test_topics_cover_salary_tech_jobs_overview_finance_and_cross():
    c = Counter(q["topic"] for q in _qs() if q["answerable"])
    assert all(c[t] >= 1 for t in ("薪資", "技術", "公司概況", "財務", "跨公司")) and c["跨公司"] == 5
    assert Counter(q["type"] for q in _qs() if q["answerable"])["職缺"] >= 1


def test_at_least_8_short_company_page_questions_without_company_name():
    short = [q for q in _qs() if q["answerable"] and q.get("company")]
    assert len(short) >= 8
    assert all(not any(c in q["question"] for c in COMPANIES) for q in short)
    assert {q["company"] for q in short} <= set(LIVE)  # 公司頁只有現場 8 家有


def test_cross_questions_use_keywords_without_single_gold_and_do_not_name_a_company():
    cross = [q for q in _qs() if q["type"] == "跨公司"]
    assert len(cross) == 6  # h21–h25 加上改標的 h40
    for q in cross:
        assert q["answerable"] and q["gold"] == [] and q["keywords"] and "company" not in q
        assert re.search("哪一?[間家]|哪些公司|哪幾[間家]", q["question"])
        assert not any(c in q["question"] for c in COMPANIES)


def test_unanswerable_have_keywords_no_gold_and_at_least_5_traps_and_cover_topics():
    un = [q for q in _qs() if not q["answerable"]]
    assert len(un) == 14 and all(q["gold"] == [] and q["absence_keywords"] for q in un)
    assert sum(q["trap"] for q in un) >= 5
    assert {"福利規章", "內部資訊", "其他公司", "語料外"} <= {q["topic"] for q in un}


def test_every_answerable_single_gold_has_file_heading_and_quote():
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

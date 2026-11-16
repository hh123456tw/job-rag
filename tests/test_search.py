"""只測檢索函式 search（與分類表）。語料是 tests/fixtures/mini 的假公司。"""
import os
from pathlib import Path

import pytest

from job_rag import classification_table, search

MINI = Path(__file__).parent / "fixtures" / "mini"


def q(text, **kw):
    kw.setdefault("corpus", MINI)
    return search(text, **kw)


def test_result_fields():
    r = q("鯨魚追蹤軟體")[0]
    assert r["company"] == "甲科技"
    assert r["file"] == "01_甲科技.md"
    assert r["heading_path"].endswith("基本資料")
    assert r["private"] is False
    assert r["score"] > 0
    assert "鯨魚" in r["text"]


def test_returns_at_most_three_ranked():
    r = q("FastAPI 工程師")
    assert 1 <= len(r) <= 3
    assert [x["score"] for x in r] == sorted((x["score"] for x in r), reverse=True)


def test_demo_mode_never_returns_private():
    # 這些詞只出現在私人段落：演示模式不得回傳任何東西
    for word in ["珊瑚礁 壓力測試", "離職率", "刺蝟密語", "狐獴密語", "企鵝密語", "河馬密語", "海豹密語", "浣熊限制"]:
        assert q(word, mode="demo") == [], word
    # 混合查詢也不能帶出私人段落
    assert all(not x["private"] for x in q("面試 風險 評價 FastAPI 工程師", k=50))


def test_demo_is_default_mode():
    assert q("刺蝟密語") == []


def test_query_mode_returns_private_flagged():
    r = q("刺蝟密語", mode="query")
    assert r and r[0]["private"] is True and r[0]["company"] == "乙資訊"


def test_company_filter_only_that_company():
    r = q("FastAPI", company="乙資訊")
    assert r and all(x["company"] == "乙資訊" for x in r)
    r = q("FastAPI", company="甲科技")
    assert r and all(x["company"] == "甲科技" for x in r)


def test_unknown_company_returns_nothing():
    assert q("FastAPI", company="不存在公司") == []


def test_unlisted_title_is_private():
    # 「風險備註」不在清單，「職缺風險」不是「職缺」的子字串匹配
    for word in ["企鵝密語", "河馬密語"]:
        r = q(word, mode="query")
        assert r and r[0]["private"] is True, word


def test_parenthetical_with_private_keyword_is_not_stripped():
    r = q("海豹密語", mode="query")
    assert r and r[0]["private"] is True


def test_public_title_with_harmless_parenthetical_is_public():
    r = q("後端工程師 PostgreSQL", company="甲科技")
    assert r and r[0]["private"] is False  # 「職缺（後端）」


def test_subheading_inherits_public_section():
    r = q("月薪四萬到六萬")
    assert r and r[0]["private"] is False


def test_private_subheading_under_judgment_section():
    r = q("離職率", mode="query")
    assert r and r[0]["private"] is True


def test_104_job_postings_public_but_limits_private():
    pub = q("Airflow dbt 貓頭鷹職缺")
    assert pub and pub[0]["file"] == "A_甲科技.md" and pub[0]["company"] == "甲科技" and not pub[0]["private"]
    assert q("浣熊限制") == []
    assert q("浣熊限制", mode="query")[0]["private"] is True


def test_battle_card_is_entirely_private_and_has_company():
    assert q("狐獴密語") == []
    r = q("狐獴密語", mode="query")
    assert r[0]["private"] is True and r[0]["company"] == "甲科技"


def test_long_section_is_split_and_tail_is_findable():
    # 「長段落」不在清單 -> 私人
    assert q("水獺密語") == []
    r = q("水獺密語", mode="query")
    assert r and r[0]["private"] is True and len(r[0]["text"]) < 1500


def test_no_match_returns_empty_not_filler():
    assert q("zzzxqv qqq 量子麵包") == []


def test_unknown_method_and_mode_raise():
    with pytest.raises(ValueError):
        q("FastAPI", method="bge-m3")
    with pytest.raises(ValueError):
        q("FastAPI", mode="secret")


def test_missing_corpus_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("JOB_RAG_CORPUS", raising=False)
    with pytest.raises(RuntimeError, match="JOB_RAG_CORPUS"):
        search("FastAPI")
    with pytest.raises(RuntimeError):
        search("FastAPI", corpus=tmp_path / "nope")


def test_corpus_path_from_env(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    assert search("鯨魚追蹤軟體")[0]["company"] == "甲科技"


def test_classification_table_rows():
    by = {(r["title"], r["private"]): r["count"] for r in classification_table(MINI)}
    assert by[("基本資料", False)] == 2  # 兩家各一段
    assert by[("風險備註", True)] == 1
    assert ("風險備註", False) not in by


@pytest.mark.skipif(not os.environ.get("JOB_RAG_CORPUS"), reason="需要完整語料")
def test_real_corpus_smoke():
    assert search("FastAPI", mode="demo")
    assert all(not x["private"] for x in search("面試 風險 評價", mode="demo", k=10))

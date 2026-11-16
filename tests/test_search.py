"""只測檢索函式 search（與分類表）。語料是 tests/fixtures/mini 的假公司。"""
import os
import shutil
from pathlib import Path

import pytest

from job_rag import classification_table, public_company_counts, retrieval, search

MINI = Path(__file__).parent / "fixtures" / "mini"


def q(text, **kw):
    kw.setdefault("corpus", MINI)
    kw.setdefault("method", "bm25")
    return search(text, **kw)


def test_result_fields():
    r = q("鯨魚追蹤軟體")[0]
    assert r["company"] == "甲科技"
    assert r["file"] == "01_甲科技.md"
    assert r["heading_path"].endswith("基本資料")
    assert "private" not in r  # 排除段落不存在，結果不需要旗標
    assert r["score"] > 0
    assert "鯨魚" in r["text"]


def test_returns_at_most_three_ranked():
    r = q("FastAPI 工程師")
    assert 1 <= len(r) <= 3
    assert [x["score"] for x in r] == sorted((x["score"] for x in r), reverse=True)


# 這些詞只出現在排除段落（含近似標題「風險備註」「職缺風險」「職缺（風險很高）」）
SECRETS = ["刺蝟密語", "狐獴密語", "企鵝密語", "河馬密語", "海豹密語", "浣熊限制", "水獺密語", "珊瑚礁 壓力測試", "離職率"]


def test_excluded_segments_are_not_in_the_index():
    for word in SECRETS:
        assert q(word) == [], word
    # 混合查詢、k 很大也帶不出排除段落
    texts = "".join(x["text"] for x in q("面試 風險 評價 FastAPI 工程師 密語 限制", k=100))
    assert not any(w in texts for w in ("刺蝟", "狐獴", "企鵝", "河馬", "海豹", "浣熊", "水獺", "珊瑚礁", "離職率"))


def test_mode_parameter_is_gone():
    with pytest.raises(TypeError):
        q("鯨魚追蹤軟體", mode="query")
    with pytest.raises(TypeError):
        q("鯨魚追蹤軟體", mode="demo")


def test_company_filter_only_that_company():
    r = q("FastAPI", company="乙資訊")
    assert r and all(x["company"] == "乙資訊" for x in r)
    r = q("FastAPI", company="甲科技")
    assert r and all(x["company"] == "甲科技" for x in r)


def test_unknown_company_returns_nothing():
    assert q("FastAPI", company="不存在公司") == []


def test_public_title_with_harmless_parenthetical_is_public():
    r = q("後端工程師 PostgreSQL", company="甲科技")
    assert r and "PostgreSQL" in r[0]["text"]  # 「職缺（後端）」


def test_subheading_inherits_public_section():
    r = q("月薪四萬到六萬")
    assert r and "月薪四萬" in r[0]["text"]


def test_104_job_postings_are_in_but_limits_section_is_out():
    pub = q("Airflow dbt 貓頭鷹職缺")
    assert pub and pub[0]["file"] == "A_甲科技.md" and pub[0]["company"] == "甲科技"
    assert q("浣熊限制") == []


def test_no_match_returns_empty_not_filler():
    assert q("zzzxqv qqq 量子麵包") == []


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        q("FastAPI", method="nope")


def test_missing_corpus_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("JOB_RAG_CORPUS", raising=False)
    with pytest.raises(RuntimeError, match="JOB_RAG_CORPUS"):
        search("FastAPI")
    with pytest.raises(RuntimeError):
        search("FastAPI", corpus=tmp_path / "nope")


def test_corpus_path_from_env(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    assert search("鯨魚追蹤軟體", method="bm25")[0]["company"] == "甲科技"


def test_classification_table_rows():
    by = {(r["title"], r["excluded"]): r["count"] for r in classification_table(MINI)}
    assert by[("基本資料", False)] == 2  # 兩家各一段
    assert by[("風險備註", True)] == 1
    assert ("風險備註", False) not in by
    assert by[("職缺風險", True)] == 1  # 近似標題不因含「職缺」而公開


def test_public_company_counts_cover_only_public_segments():
    c = public_company_counts(MINI)
    assert c["乙資訊"] == 2 and "綜合" not in c  # 基本資料、職缺；工作評價被排除
    assert sum(c.values()) == sum(r["count"] for r in classification_table(MINI) if not r["excluded"])


# ---- 公司歸屬：跨公司檔裡的段落依標題路徑或檔名歸到公司 ----
@pytest.fixture
def mixed_corpus(tmp_path, monkeypatch):
    c = tmp_path / "c"
    shutil.copytree(MINI, c)
    monkeypatch.setitem(retrieval.ALIASES, "甲科", "甲科技")  # 檔名簡稱
    (c / "104" / "補2_甲科.md").write_text("# 補2 甲科\n\n## 二、職缺\n獨特詞彙：獨角獸職缺。\n", encoding="utf-8")
    (c / "104" / "E_甲科_乙資訊.md").write_text(
        "# E 甲科 乙資訊\n\n## 職缺\n獨特詞彙：海龜職缺。\n\n## 甲科技股份有限公司\n### 1. 職缺\n獨特詞彙：海星職缺。\n",
        encoding="utf-8")
    return c


def test_file_name_with_one_company_assigns_that_company(mixed_corpus):
    r = q("獨角獸職缺", corpus=mixed_corpus)
    assert r and r[0]["company"] == "甲科技"
    assert q("獨角獸職缺", company="甲科技", corpus=mixed_corpus)


def test_title_path_company_beats_ambiguous_file_name(mixed_corpus):
    r = q("海星職缺", company="甲科技", corpus=mixed_corpus)
    assert r and "海星" in r[0]["text"]


def test_ambiguous_file_and_no_company_in_title_stays_general(mixed_corpus):
    # 檔名有兩家公司、標題沒有公司：不猜，歸「綜合」；選任何一家都搜不到
    r = q("海龜職缺", corpus=mixed_corpus)
    assert r and r[0]["company"] == "綜合"
    for c in ("甲科技", "乙資訊"):
        assert not any("海龜" in x["text"] for x in q("海龜職缺", company=c, corpus=mixed_corpus, k=50))


@pytest.mark.skipif(not os.environ.get("JOB_RAG_CORPUS"), reason="需要完整語料")
def test_real_corpus_smoke():
    assert search("FastAPI", method="bm25")
    assert "綜合" not in public_company_counts()  # 公開段落都歸得到公司

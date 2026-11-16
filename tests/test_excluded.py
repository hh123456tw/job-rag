"""票 23：移出名單（EXCLUDED_COMPANIES）。名單內的公司整家略過：索引、檢索、偵測、清單、提示都找不到。
合成語料用名單內的真名字（奧衍、尼諾思科技、醫宇宙）；完整語料的測試要設 JOB_RAG_REAL_CORPUS。"""
import os
import re
from pathlib import Path

import pytest

from job_rag import detect_company, public_company_counts, retrieval, search
from job_rag.topics import topics
from tests.test_vector import FakeModel, fake_env  # noqa: F401  (autouse fixture)

ROOT = Path(__file__).parent.parent
THREE = ["奧衍", "尼諾思科技", "醫宇宙"]
ALIAS = ["奧衍", "尼諾思", "醫宇宙"]  # 問句裡可能出現的寫法


@pytest.fixture
def corpus(tmp_path):
    c = tmp_path / "c"
    (c / "104").mkdir(parents=True)
    (c / "S1_甲科技.md").write_text("# 甲科技\n## 1. 基本資料\n甲科技做雲端平台，獨特詞彙：貓熊。\n", encoding="utf-8")
    (c / "S2_乙資訊.md").write_text("# 乙資訊\n## 1. 基本資料\n乙資訊做資安。\n## 4. 職缺\n乙資訊徵工程師。\n", encoding="utf-8")  # 讓 BM25 的詞頻不會剛好過半
    (c / "S3_奧衍.md").write_text("# 奧衍\n## 1. 基本資料\n奧衍做流程自動化，獨特詞彙：河豚。\n## 4. 職缺\n奧衍徵 RPA 工程師，獨特詞彙：海馬。\n", encoding="utf-8")
    (c / "S4_尼諾思科技.md").write_text("# 尼諾思科技\n## 1. 基本資料\n尼諾思做機器人，獨特詞彙：水母。\n", encoding="utf-8")
    (c / "S5_醫宇宙.md").write_text("# 醫宇宙\n## 1. 基本資料\n醫宇宙做遠距健康，獨特詞彙：海龍。\n", encoding="utf-8")
    # 跨公司 104 檔：標題決定公司；別名「尼諾思」要能歸到尼諾思科技（再被略過），不能掉進「綜合」
    (c / "104" / "E_甲科_尼諾思_醫宇宙.md").write_text(
        "# E\n## 1. 甲科技股份有限公司\n### 目前開放職缺\n甲科技徵後端，獨特詞彙：海星。\n"
        "## 2. 尼諾思智慧科技股份有限公司\n### 目前開放職缺\n尼諾思徵韌體，獨特詞彙：海膽。\n"
        "## 3. 醫宇宙遠距健康科技股份有限公司\n### 目前開放職缺\n醫宇宙徵前端，獨特詞彙：海葵。\n", encoding="utf-8")
    return c


UNIQUE = ["河豚", "海馬", "水母", "海龍", "海膽", "海葵"]  # 只出現在三家的段落


def test_default_list_is_exactly_the_three():
    assert set(retrieval.EXCLUDED_COMPANIES) == set(THREE)


def test_excluded_companies_are_not_in_the_index(corpus):
    assert public_company_counts(corpus) == {"甲科技": 2, "乙資訊": 2}  # 沒有三家，也沒有掉進「綜合」
    assert not any(c in retrieval.classification_table(corpus) for c in [])  # 分類表也不含（下一行逐項查）
    assert all(not any(w in r["title"] for w in THREE) for r in retrieval.classification_table(corpus))


@pytest.mark.parametrize("method", retrieval.METHODS)
@pytest.mark.parametrize("word", UNIQUE)
def test_no_method_finds_an_excluded_company(corpus, method, word):
    for company in (None, "奧衍", "尼諾思科技", "醫宇宙"):
        r = search(word, method=method, company=company, corpus=corpus, k=50, gate=False)
        assert not [x for x in r if x["company"] in THREE or word in x["text"]]


def test_included_company_still_found_negative_control(corpus):
    # 負向對照：同一份語料裡沒被移出的公司照樣找得到，所以上面的「找不到」不是搜尋壞了
    assert search("貓熊", method="bm25", corpus=corpus)[0]["company"] == "甲科技"
    assert search("海星", method="bm25", corpus=corpus)[0]["company"] == "甲科技"


def test_detection_and_mentions_ignore_excluded_names(corpus):
    for name in ALIAS:
        assert detect_company(f"{name}是做什麼的？", corpus) is None
        assert not retrieval.mentions_company(f"{name}有哪些職缺？", corpus)
    assert detect_company("甲科技是做什麼的？", corpus) == "甲科技"  # 負向對照


def test_topics_for_excluded_company_is_empty(corpus):
    assert topics("奧衍", corpus)["segments"] == 0


def test_list_drives_the_exclusion(corpus, monkeypatch):
    # 名單是唯一的開關：清空後三家回來，改成別家就換別家被略過
    monkeypatch.setattr(retrieval, "EXCLUDED_COMPANIES", frozenset())
    retrieval._parse.cache_clear(), retrieval._public.cache_clear()
    assert set(public_company_counts(corpus)) == {"甲科技", "乙資訊", *THREE}
    monkeypatch.setattr(retrieval, "EXCLUDED_COMPANIES", frozenset({"甲科技"}))
    retrieval._parse.cache_clear(), retrieval._public.cache_clear()
    assert set(public_company_counts(corpus)) == {"乙資訊", *THREE}


def test_vector_cache_key_changes_when_the_list_changes(corpus, monkeypatch, tmp_path):
    cache = Path(os.environ["JOB_RAG_CACHE"])
    search("貓熊", method="bge-m3", corpus=corpus)
    first = {f.name for f in cache.glob("bge-m3_*.npy")}
    monkeypatch.setattr(retrieval, "EXCLUDED_COMPANIES", frozenset({"奧衍", "尼諾思科技"}))  # 醫宇宙回來
    for f in (retrieval._parse, retrieval._public, retrieval._bm25, retrieval._index):
        f.cache_clear()
    FakeModel.calls = []
    search("貓熊", method="bge-m3", corpus=corpus)
    second = {f.name for f in cache.glob("bge-m3_*.npy")}
    assert len(second - first) == 1  # 新鍵、新檔：不會拿舊名單的向量來用
    texts = [t for _, ts in FakeModel.calls for t in ts]
    assert any("醫宇宙" in t for t in texts)  # 真的重新編碼了


def test_sample_corpus_is_not_affected():
    # 公開範例語料（sample_corpus/）是獨立的示範資料，不受名單影響
    assert set(public_company_counts(ROOT / "sample_corpus")) == {"奧衍", "尼諾思科技", "遠振資訊"}


def test_sample_corpus_exemption_is_by_location_and_search_finds_the_sample_companies(tmp_path):
    # 名單只對「不是 sample_corpus/」的語料生效；範例檔 S1_奧衍、S2_尼諾思科技是名單內的公司名，卻必須照常載入與檢索
    import shutil
    sample = ROOT / "sample_corpus"
    assert {"S1_奧衍.md", "S2_尼諾思科技.md"} <= {f.name for f in sample.glob("*.md")}
    for name in ("奧衍", "尼諾思科技"):
        hits = search(f"{name}是做什麼的？", method="bm25", corpus=sample, k=5, gate=False)
        assert name in {h["company"] for h in hits}
    copy = tmp_path / "elsewhere"
    shutil.copytree(sample, copy)
    assert set(public_company_counts(copy)) == {"遠振資訊"}  # 負向對照：搬到別處就是普通語料，三家名單生效


@pytest.mark.skipif(not os.environ.get("JOB_RAG_REAL_CORPUS"), reason="需要完整語料（JOB_RAG_REAL_CORPUS）")
def test_real_corpus_has_none_of_the_three():
    real = os.environ["JOB_RAG_REAL_CORPUS"]
    counts = public_company_counts(real)
    assert not set(THREE) & set(counts) and "綜合" not in counts
    assert len(counts) == 13
    for q in ("奧衍是做什麼的？", "尼諾思有哪些職缺？", "醫宇宙的技術堆疊", "UiPath RPA 解決方案架構師", "遠距健康 醫療 AI"):
        for m in ("bm25", "bge-m3"):
            assert not [h for h in search(q, method=m, corpus=real, k=50, gate=False) if h["company"] in THREE]


def test_no_shipped_data_names_an_excluded_company():
    """預設題目、評估題、追問題：題目文字、範圍、金標標題都不含三家（檔名不算：跨公司 104 檔的檔名本來就含）。"""
    import json
    presets = json.loads((ROOT / "job_rag" / "company_presets.json").read_text(encoding="utf-8"))
    assert not set(ALIAS) & set(presets["companies"])
    text = json.dumps(presets, ensure_ascii=False)
    assert not [n for n in ALIAS if n in text]
    for rel in ("eval/questions.json", "eval/followups.json"):
        if not (ROOT / rel).exists():
            continue  # 公開版沒有完整題組與追問題
        for q in json.loads((ROOT / rel).read_text(encoding="utf-8"))["questions"]:
            flat = " ".join([q["question"], q.get("company", ""), q.get("previous", "")] +
                            [g["heading"] + g["quote"] for g in q["gold"]])
            assert not [n for n in ALIAS if n in flat], (rel, q["id"])
            assert not [g for g in q["gold"] if re.match(r"^(08|10|11)_", g["file"])], (rel, q["id"])

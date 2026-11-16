"""向量檢索與混合：全部用假嵌入器，不需要下載模型。真模型測試要設 JOB_RAG_MODELS_TEST=1。"""
import os
import zlib
from pathlib import Path

import numpy as np
import pytest

from job_rag import retrieval, search
from job_rag.retrieval import METHODS, rrf

MINI = Path(__file__).parent / "fixtures" / "mini"
VECTOR = ["bge-small-zh", "bge-m3", "e5-large"]


class FakeModel:
    """字元雙連詞雜湊成 128 維向量。同一批文字永遠得到同一組向量。記錄收到的文字。"""
    calls: list = []

    def __init__(self, name):
        self.name = name

    def encode(self, texts, **kw):
        FakeModel.calls.append((self.name, list(texts)))
        out = np.zeros((len(texts), 128), dtype="float32")
        for i, t in enumerate(texts):
            t = t.removeprefix("query: ").removeprefix("passage: ")  # 前綴不當內容
            for a, b in zip(t, t[1:]):
                out[i, zlib.crc32((a + b).encode()) % 128] += 1
        return out  # 故意不正規化：由 search() 負責正規化


@pytest.fixture(autouse=True)
def fake_env(monkeypatch, tmp_path):
    FakeModel.calls = []
    monkeypatch.setenv("JOB_RAG_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(retrieval, "_load_model", lambda method: FakeModel(method))
    retrieval._index.cache_clear()
    yield
    retrieval._index.cache_clear()


def q(text, **kw):
    kw.setdefault("corpus", MINI)
    return search(text, **kw)


# ---- RRF：手算 ----
def test_rrf_hand_worked_example():
    # A: d1,d2,d3  B: d2,d3,d1  k=60
    # d1 = 1/61 + 1/63；d2 = 1/62 + 1/61；d3 = 1/63 + 1/62
    ranked = rrf([["d1", "d2", "d3"], ["d2", "d3", "d1"]])
    out = dict(ranked)
    assert out["d1"] == pytest.approx(1 / 61 + 1 / 63)
    assert out["d2"] == pytest.approx(1 / 61 + 1 / 62)
    assert out["d3"] == pytest.approx(1 / 62 + 1 / 63)
    assert [d for d, _ in ranked] == ["d2", "d1", "d3"]


def test_rrf_item_in_one_list_only_gets_one_term():
    out = dict(rrf([["a", "b"], ["c"]]))
    assert out["b"] == pytest.approx(1 / 62)
    assert out["c"] == pytest.approx(1 / 61)


# ---- 各方式都能找到對的段落 ----
@pytest.mark.parametrize("method", METHODS)
def test_every_method_finds_the_obvious_segment(method):
    r = q("鯨魚追蹤軟體", method=method)
    assert r and r[0]["company"] == "甲科技" and r[0]["heading_path"].endswith("基本資料")
    assert set(r[0]) >= {"company", "file", "heading_path", "private", "text", "score"}


def test_methods_list():
    assert METHODS == ("bm25", "bge-small-zh", "bge-m3", "e5-large", "hybrid")


# ---- 模式與公司過濾：每一種方式 ----
@pytest.mark.parametrize("method", METHODS)
def test_demo_mode_never_returns_private_for_any_method(method):
    secrets = ("刺蝟密語", "狐獴密語", "企鵝密語", "浣熊限制")
    for word in [*secrets, "珊瑚礁 壓力測試", "離職率"]:
        res = q(word, method=method, mode="demo", k=100)
        assert res or method == "bm25", (method, word)  # 向量方式一定有結果，但必須全是公開段落
        assert all(not x["private"] for x in res), (method, word)
        assert not any(w in x["text"] for x in res for w in secrets), (method, word)


@pytest.mark.parametrize("method", METHODS)
def test_query_mode_can_return_private_for_any_method(method):
    r = q("刺蝟密語", method=method, mode="query")
    assert r and r[0]["private"] is True and r[0]["company"] == "乙資訊"


@pytest.mark.parametrize("method", METHODS)
def test_company_filter_for_any_method(method):
    for c in ("甲科技", "乙資訊"):
        r = q("FastAPI", method=method, company=c, k=50)
        assert r and all(x["company"] == c for x in r), (method, c)
    assert q("FastAPI", method=method, company="不存在公司") == []


@pytest.mark.parametrize("method", VECTOR + ["hybrid"])
def test_company_filter_applies_before_cutoff(method):
    # 最像的段落是甲科技的；只看乙資訊、k=1 時，仍要回乙資訊的結果
    r = q("鯨魚追蹤軟體", method=method, company="乙資訊", k=1)
    assert len(r) == 1 and r[0]["company"] == "乙資訊"


@pytest.mark.parametrize("method", VECTOR)
def test_vector_scores_are_cosine_and_descending(method):
    r = q("鯨魚追蹤軟體", method=method, k=5)
    s = [x["score"] for x in r]
    assert s == sorted(s, reverse=True) and all(-1.0001 <= v <= 1.0001 for v in s)
    assert len(r) == 5  # 向量檢索不像 BM25 會因為零分而少回


def test_vector_query_with_unrelated_text_still_returns_k():
    # 沒有查無門檻（之後的票）：向量檢索一律回 k 個
    assert len(q("zzzxqv qqq 量子麵包", method="bge-m3")) == 3


# ---- 混合 ----
def test_hybrid_score_is_rrf_of_bm25_and_bge_m3():
    b = q("鯨魚追蹤軟體", method="bm25", k=100)
    v = q("鯨魚追蹤軟體", method="bge-m3", k=100)
    top = q("鯨魚追蹤軟體", method="hybrid", k=1)[0]
    key = lambda x: (x["file"], x["heading_path"], x["text"])
    rb = {key(x): i for i, x in enumerate(b, 1)}
    rv = {key(x): i for i, x in enumerate(v, 1)}
    want = {k: (1 / (60 + rb[k]) if k in rb else 0) + 1 / (60 + rv[k]) for k in rv}
    assert top["score"] == pytest.approx(max(want.values()))
    assert want[key(top)] == pytest.approx(max(want.values()))


# ---- 前綴與快取 ----
def test_e5_adds_query_and_passage_prefixes_others_do_not():
    q("鯨魚追蹤軟體", method="e5-large")
    texts = [t for name, ts in FakeModel.calls if name == "e5-large" for t in ts]
    assert "query: 鯨魚追蹤軟體" in texts
    passages = [t for t in texts if t != "query: 鯨魚追蹤軟體"]
    assert passages and all(t.startswith("passage: ") for t in passages)
    FakeModel.calls = []
    q("鯨魚追蹤軟體", method="bge-m3")
    texts = [t for _, ts in FakeModel.calls for t in ts]
    assert "鯨魚追蹤軟體" in texts and not any(t.startswith(("query: ", "passage: ")) for t in texts)


def test_passage_vectors_are_cached_on_disk_not_recomputed():
    q("鯨魚追蹤軟體", method="bge-m3")
    assert sum(len(ts) for _, ts in FakeModel.calls) > 1
    retrieval._index.cache_clear()  # 模擬重開程式：只剩磁碟快取
    FakeModel.calls = []
    q("珊瑚礁", method="bge-m3", mode="query")
    assert sum(len(ts) for _, ts in FakeModel.calls) == 1  # 只編碼查詢


def test_cache_invalidated_when_corpus_text_changes(tmp_path):
    import shutil
    c = tmp_path / "c"
    shutil.copytree(MINI, c)
    q("鯨魚", method="bge-m3", corpus=c)
    f = c / "01_甲科技.md"
    f.write_text(f.read_text(encoding="utf-8") + "\n## 5. 技術堆疊\n新增獨特詞彙：樹懶。\n", encoding="utf-8")
    retrieval._segments.cache_clear()
    retrieval._index.cache_clear()
    FakeModel.calls = []
    q("鯨魚", method="bge-m3", corpus=c)
    assert sum(len(ts) for _, ts in FakeModel.calls) > 1  # 內容變了，重算


def test_search_makes_no_network_call(monkeypatch):
    import socket

    def boom(*a, **k):
        raise AssertionError("檢索不得連網")
    monkeypatch.setattr(socket.socket, "connect", boom)
    for m in METHODS:
        q("鯨魚追蹤軟體", method=m)


@pytest.mark.skipif(not os.environ.get("JOB_RAG_MODELS_TEST"), reason="需要下載的真模型；設 JOB_RAG_MODELS_TEST=1")
@pytest.mark.parametrize("method", VECTOR)
def test_real_model_smoke(monkeypatch, tmp_path, method):
    monkeypatch.undo()  # 還原成真的 _load_model
    monkeypatch.setenv("JOB_RAG_CACHE", str(tmp_path / "real"))
    retrieval._index.cache_clear()
    r = search("鯨魚追蹤軟體在哪裡", method=method, corpus=MINI)
    assert r and r[0]["company"] == "甲科技"

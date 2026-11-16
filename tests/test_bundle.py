"""公開版語料包：匯出只含公開事實段落；用語料包檢索與用原始語料檢索結果相同；對不上要報錯。"""
import json
import os
from pathlib import Path

import numpy as np
import pytest

from job_rag import retrieval, search
from job_rag.evalset import questions_path
from job_rag.export_bundle import export_bundle
from tests.test_vector import FakeModel, _clear

MINI = Path(__file__).parent / "fixtures" / "mini"
# 排除段落的獨特詞彙（含「近似標題」：風險備註、職缺風險、職缺（風險很高）、面試行）
EXCLUDED_WORDS = ["狐獴密語", "企鵝密語", "河馬密語", "海豹密語", "刺蝟密語", "麋鹿面試", "珊瑚礁", "離職率", "壓力測試"]
QUESTIONS = ["鯨魚追蹤軟體", "FastAPI 後端 職缺", "月薪", "物流排程系統", "駱駝面談", "Docker 技術堆疊"]


@pytest.fixture(autouse=True)
def fake_env(monkeypatch, tmp_path):
    FakeModel.calls = []
    monkeypatch.setenv("JOB_RAG_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("JOB_RAG_BUNDLE", raising=False)
    monkeypatch.setattr(retrieval, "_load_model", lambda method: FakeModel(method))
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.0)
    _clear()
    yield
    _clear()


@pytest.fixture
def bundle(tmp_path):
    out = tmp_path / "bundle"
    export_bundle(MINI, out)
    return out


def _texts(out: Path) -> str:
    return (out / "segments.jsonl").read_text(encoding="utf-8")


def _use(monkeypatch, out):
    monkeypatch.setenv("JOB_RAG_BUNDLE", str(out))
    _clear()


def test_bundle_has_public_segments_only(bundle):
    rows = [json.loads(l) for l in _texts(bundle).splitlines()]
    assert rows and set(rows[0]) == {"company", "file", "heading_path", "text"}
    blob = "\n".join(r["text"] for r in rows)
    for w in EXCLUDED_WORDS:
        assert w not in blob, w
    assert "鯨魚追蹤軟體" in blob and "駱駝面談" in blob  # 近似字「面談」不是面試，要留


def test_bundle_vectors_match_segment_count(bundle):
    z = np.load(bundle / "vectors.npz")
    assert z["vectors"].shape[0] == len(_texts(bundle).splitlines())


@pytest.mark.parametrize("method", ["bm25", "bge-m3", "hybrid"])
def test_bundle_search_equals_corpus_search(method, bundle, monkeypatch):
    want = {x: search(x, method=method, corpus=MINI, k=10) for x in QUESTIONS}
    _clear()
    FakeModel.calls = []
    monkeypatch.delenv("JOB_RAG_CORPUS", raising=False)
    _use(monkeypatch, bundle)
    got = {x: search(x, method=method, k=10) for x in QUESTIONS}
    assert got == want
    assert all(len(texts) == 1 for _, texts in FakeModel.calls)  # 只編碼查詢句，沒有編碼段落


def test_bundle_search_never_returns_excluded(bundle, monkeypatch):
    _use(monkeypatch, bundle)
    for w in EXCLUDED_WORDS:
        assert not any(w in r["text"] for r in search(w, method="bm25", k=50))


def test_unset_bundle_still_needs_corpus(monkeypatch):
    monkeypatch.delenv("JOB_RAG_CORPUS", raising=False)
    with pytest.raises(RuntimeError, match="JOB_RAG_CORPUS"):
        search("x", method="bm25")


def test_tampered_segment_text_is_rejected(bundle, monkeypatch):
    f = bundle / "segments.jsonl"
    f.write_text(f.read_text(encoding="utf-8").replace("鯨魚", "海豚", 1), encoding="utf-8")
    _use(monkeypatch, bundle)
    with pytest.raises(RuntimeError, match="雜湊"):
        search("鯨魚", method="bm25")


def test_vectors_with_wrong_hash_are_rejected(bundle, monkeypatch):
    z = dict(np.load(bundle / "vectors.npz"))
    z["segments_sha1"] = np.array("0" * 16)
    np.savez(bundle / "vectors.npz", **z)
    _use(monkeypatch, bundle)
    with pytest.raises(RuntimeError, match="雜湊"):
        search("鯨魚", method="bge-m3")


def test_vectors_with_wrong_row_count_are_rejected(bundle, monkeypatch):
    z = dict(np.load(bundle / "vectors.npz"))
    z["vectors"] = z["vectors"][:-1]
    np.savez(bundle / "vectors.npz", **z)
    _use(monkeypatch, bundle)
    with pytest.raises(RuntimeError, match="筆數"):
        search("鯨魚", method="bge-m3")


def test_missing_bundle_folder_is_an_error(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path / "nope")
    with pytest.raises(RuntimeError, match="JOB_RAG_BUNDLE"):
        search("x", method="bm25")


def test_bundle_has_only_bge_m3_vectors(bundle, monkeypatch):
    _use(monkeypatch, bundle)
    with pytest.raises(RuntimeError, match="bge-m3"):
        search("鯨魚", method="e5-large")


# ---- 真語料：全文比對（沒設 JOB_RAG_REAL_CORPUS 就跳過）----
@pytest.mark.skipif(not os.environ.get("JOB_RAG_REAL_CORPUS"), reason="需要完整語料（JOB_RAG_REAL_CORPUS）")
def test_real_bundle_contains_no_excluded_text(tmp_path):
    corpus = os.environ["JOB_RAG_REAL_CORPUS"]
    out = tmp_path / "b"
    export_bundle(corpus, out)
    root = str(Path(corpus).resolve())
    blob = "\n".join(json.loads(l)["text"] for l in _texts(out).splitlines())
    public_blob = "\n".join(s["text"] for s in retrieval._public(root))
    excluded = [s for s in retrieval._segments(root) if s["excluded"]]
    assert excluded
    leaked = []
    for s in excluded:
        for line in s["text"].splitlines():
            line = line.strip()
            # 過短的行（如「無」「—」）太通用；同一行也出現在公開段落時，屬公開內容
            if len(line) >= 12 and line not in public_blob and line in blob:
                leaked.append(line[:30])
    assert not leaked, leaked[:5]
    assert not [s for s in excluded if len(s["text"]) >= 12 and s["text"] not in public_blob and s["text"] in blob]


@pytest.mark.skipif(not (os.environ.get("JOB_RAG_MODELS_TEST") and os.environ.get("JOB_RAG_REAL_CORPUS")), reason="需要真模型與真語料（JOB_RAG_REAL_CORPUS）")
def test_real_model_bundle_ranks_equal_corpus_ranks(tmp_path, monkeypatch):
    monkeypatch.undo()  # 用真模型：移除假嵌入器
    _clear()
    out = tmp_path / "b"
    export_bundle(os.environ["JOB_RAG_REAL_CORPUS"], out)
    qs = [e["question"] for e in json.loads(questions_path().read_text(encoding="utf-8"))["questions"]][:8]
    assert len(qs) >= 5
    want = [search(x, method=m, k=5, gate=False) for x in qs for m in ("bge-m3", "hybrid")]
    _clear()
    monkeypatch.setenv("JOB_RAG_BUNDLE", str(out))
    got = [search(x, method=m, k=5, gate=False) for x in qs for m in ("bge-m3", "hybrid")]
    for a, b in zip(got, want):
        assert [r["text"] for r in a] == [r["text"] for r in b]
        assert [r["score"] for r in a] == pytest.approx([r["score"] for r in b], abs=1e-5)

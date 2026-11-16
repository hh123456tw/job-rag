"""票 24：展示／自用兩個索引。混合語料（公開＋私人段落＋面經）；展示模式零洩漏、行為與只有公開的語料完全相同。"""
import json

import pytest

from job_rag import retrieval, search
from job_rag.retrieval import METHODS
from tests.test_vector import FakeModel, fake_env  # noqa: F401  (autouse fixture)

SECRET = "紫羅蘭私房"   # 只在私人段落
IV = "斑馬面試官"       # 只在面經
PUBLIC_MD = "# 甲科技\n## 1. 基本資料\n甲科技做雲端平台，獨特詞彙：貓熊。\n## 4. 職缺\n甲科技徵後端工程師。\n"
PRIVATE_MD = f"## 6. 面談作戰卡\n作戰：{SECRET} 要問薪資。\n面試：第二關是主管。\n## 7. 風險\n風險：{SECRET} 出差多。\n"


def _write(root, text):
    root.mkdir(parents=True, exist_ok=True)
    (root / "S1_甲科技.md").write_text(text, encoding="utf-8")
    (root / "S2_乙資訊.md").write_text("# 乙資訊\n## 1. 基本資料\n乙資訊做資安。\n## 4. 職缺\n乙資訊徵工程師。\n", encoding="utf-8")
    return root


@pytest.fixture
def mixed(tmp_path, monkeypatch):
    c = _write(tmp_path / "mixed", PUBLIC_MD + PRIVATE_MD)
    sd = tmp_path / "selfdata" / "面經" / "goodjob"
    sd.mkdir(parents=True)
    row = {"source": "goodjob.life", "company": "甲科技", "interview_time": "2024-05", "job_title": "後端", "locked": False,
           "window_ok": True, "sections": [{"subtitle": "面試過程", "content": f"{IV} 問了資料庫。"}], "interview_qas": []}
    (sd / "甲科技.jsonl").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("JOB_RAG_SELF_DIR", str(tmp_path / "selfdata"))
    return c


@pytest.fixture
def public_only(tmp_path):
    return _write(tmp_path / "pub", PUBLIC_MD)


def texts(r):
    return json.dumps(r, ensure_ascii=False)


@pytest.mark.parametrize("method", METHODS)
def test_demo_never_returns_private_text_even_for_exact_queries(mixed, method):
    for word in (SECRET, IV, "面談作戰卡", "面試：第二關是主管"):
        r = search(word, method=method, corpus=mixed, k=50, gate=False)
        assert SECRET not in texts(r) and IV not in texts(r) and "第二關" not in texts(r) and "作戰" not in texts(r), (method, word)
    assert search(SECRET, method=method, corpus=mixed, k=50, gate=False, mode="demo") == search(SECRET, method=method, corpus=mixed, k=50, gate=False)


@pytest.mark.parametrize("method", METHODS)
def test_demo_results_are_identical_to_a_public_only_corpus(mixed, public_only, method):
    for question in ("甲科技做什麼", "職缺", SECRET, "乙資訊徵工程師"):
        a = search(question, method=method, corpus=mixed, k=50, gate=False, dedupe=True)
        b = search(question, method=method, corpus=public_only, k=50, gate=False, dedupe=True)
        assert [(r["company"], r["heading_path"], r["text"], r["score"]) for r in a] == \
               [(r["company"], r["heading_path"], r["text"], r["score"]) for r in b], (method, question)


@pytest.mark.parametrize("method", ("bm25", "bge-m3"))
def test_self_mode_finds_private_notes_and_interviews(mixed, method):
    r = search(SECRET, method=method, corpus=mixed, k=50, gate=False, mode="self")
    assert any(SECRET in x["text"] for x in r)
    top = search(IV, method="bm25", corpus=mixed, k=3, gate=False, mode="self")[0]
    assert IV in top["text"] and top["private"] is True and top["company"] == "甲科技"
    assert any("面試：第二關是主管" in x["text"] for x in search("第二關主管", method="bm25", corpus=mixed, k=50, gate=False, mode="self"))


def test_self_mode_keeps_public_segments_too_and_marks_them_not_private(mixed):
    r = search("貓熊", method="bm25", corpus=mixed, mode="self")
    assert r[0]["company"] == "甲科技" and r[0]["private"] is False


def test_demo_results_have_no_private_key_and_unknown_mode_is_rejected(mixed):
    assert all("private" not in x for x in search("貓熊", corpus=mixed, gate=False))
    for bad in ("admin", "../self", "SELF", "", None):
        with pytest.raises(ValueError):
            search("貓熊", corpus=mixed, mode=bad)


def test_company_counts_follow_mode(mixed):
    assert retrieval.public_company_counts(mixed) == {"乙資訊": 2, "甲科技": 2}
    assert retrieval.public_company_counts(mixed, mode="self")["甲科技"] > 2


def test_vector_cache_keys_are_separate_and_demo_key_is_unchanged(mixed, tmp_path):
    search("貓熊", method="bge-m3", corpus=mixed, gate=False)
    search("貓熊", method="bge-m3", corpus=mixed, gate=False, mode="self")
    names = sorted(p.name for p in (tmp_path / "cache").glob("*.npy"))
    assert len(names) == 2 and sum("_self_" in n for n in names) == 1
    h = retrieval.segments_hash(s["_index"] for s in retrieval._public(retrieval._root(mixed)))
    assert [n for n in names if "_self_" not in n] == [f"bge-m3_{h}.npy"]


def test_demo_encoder_never_sees_private_text(mixed):
    search("貓熊", method="bge-m3", corpus=mixed, gate=False)
    seen = " ".join(t for _, ts in FakeModel.calls for t in ts)
    assert SECRET not in seen and IV not in seen


def test_no_self_dir_still_gives_private_notes(mixed, monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_RAG_SELF_DIR", str(tmp_path / "nope"))
    r = search(SECRET, method="bm25", corpus=mixed, k=5, gate=False, mode="self")
    assert any(SECRET in x["text"] for x in r) and not any(IV in x["text"] for x in r)

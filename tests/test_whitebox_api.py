"""票 28：白盒化的後端欄位。/api/search 帶 score、threshold、search_ms；/api/answer 帶 answer_ms、usage（有才帶）。
usage 的數字都是測試替身給的假值，只用來驗證欄位有被傳出來。"""
import pytest

from job_rag import guard, retrieval, search
from job_rag.answer import answer
from tests.test_answer import FakePost, MINI, PUB  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

Q = "鯨魚追蹤軟體"


class UsagePost(FakePost):
    def __init__(self, usage, reply="答案 [1]"):
        super().__init__(reply)
        self.usage = usage

    def __call__(self, *a):
        r = super().__call__(*a)
        return r | ({"usage": self.usage} if self.usage is not None else {})


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")  # 假的，替身不會連網


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    for k in ("JOB_RAG_ACCESS_CODE", "JOB_RAG_ANSWER_LIMIT", "JOB_RAG_FAKE_ANSWER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    return appmod


def test_search_scores_equal_retrieval_scores_and_carry_threshold(web, monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.123)
    c = web.app.test_client()
    d = c.get("/api/search", query_string={"q": Q, "company": "甲科技"}).get_json()
    want = search(Q, corpus=MINI, company="甲科技", gate=False, dedupe=True)
    assert [h["score"] for h in d["hits"]] == [h["score"] for h in want]  # 同一個數字，不重算
    assert d["threshold"] == round(0.123 - retrieval.SCOPED_DROP, 3) and d["cross"] is False
    monkeypatch.setattr(retrieval, "CROSS_FLOOR", 0.321)
    x = c.get("/api/search", query_string={"q": Q}).get_json()  # 沒指定公司：跨公司路徑，帶它自己的門檻
    assert x["cross"] is True and x["threshold"] == 0.321 and x["threshold"] != d["threshold"]


def test_search_ms_is_non_negative_number(web):
    d = web.app.test_client().get("/api/search", query_string={"q": Q}).get_json()
    assert isinstance(d["search_ms"], (int, float)) and d["search_ms"] >= 0
    assert {"company", "file", "heading_path", "text", "also_in"} <= set(d["hits"][0])  # 既有欄位仍在


def test_search_omits_score_when_default_method_has_no_comparable_score(web, monkeypatch):
    monkeypatch.setattr(retrieval, "DEFAULT_METHOD", "bm25")
    monkeypatch.setattr(web.retrieval, "DEFAULT_METHOD", "bm25")
    d = web.app.test_client().get("/api/search", query_string={"q": Q}).get_json()
    assert d["hits"] and all("score" not in h for h in d["hits"])


def test_answer_carries_answer_ms_and_usage_when_present(web, monkeypatch):
    monkeypatch.setattr(web, "_post", UsagePost({"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}))
    d = web.app.test_client().get("/api/answer", query_string={"q": Q}).get_json()
    assert d["status"] == "ok" and d["answer"] == "答案 [1]" and d["sources"]
    assert d["usage"] == {"prompt_tokens": 11, "completion_tokens": 7}
    assert isinstance(d["answer_ms"], (int, float)) and d["answer_ms"] >= 0


def test_answer_has_no_usage_key_when_deepseek_gave_none(web, monkeypatch):
    monkeypatch.setattr(web, "_post", UsagePost(None))
    d = web.app.test_client().get("/api/answer", query_string={"q": Q}).get_json()
    assert d["status"] == "ok" and "usage" not in d and d["answer_ms"] >= 0


@pytest.mark.parametrize("bad", [{}, {"prompt_tokens": "x"}, "oops", {"prompt_tokens": True}, {"prompt_tokens": -1}])
def test_answer_drops_unusable_usage(bad):
    r = answer("問題", [PUB], post=UsagePost(bad))
    assert "usage" not in r and r["answer"] == "答案 [1]"


def test_answer_keeps_only_the_field_that_exists():
    r = answer("問題", [PUB], post=UsagePost({"prompt_tokens": 5}))
    assert r["usage"] == {"prompt_tokens": 5}


def test_answer_structure_unchanged_without_usage():
    assert set(answer("問題", [PUB], post=FakePost())) == {"answer", "sources"}


def test_fake_usage_mode_gives_fake_usage_and_default_ok_gives_none(web, monkeypatch):
    c = web.app.test_client()
    monkeypatch.setenv("JOB_RAG_FAKE_ANSWER", "ok")
    assert "usage" not in c.get("/api/answer", query_string={"q": Q}).get_json()
    monkeypatch.setenv("JOB_RAG_FAKE_ANSWER", "usage")  # 替身：假 usage，只供 UI 測試
    assert c.get("/api/answer", query_string={"q": Q}).get_json()["usage"] == {"prompt_tokens": 1234, "completion_tokens": 56}

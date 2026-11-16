"""票 22：/api/search 與 /api/answer 的 history 參數。DeepSeek 用替身；伺服器不存對話。"""
import json

import pytest

from job_rag import guard, retrieval
from tests.test_answer import MINI, FakePost  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

HIST = json.dumps([{"q": "甲科技有哪些職缺？", "a": "徵後端工程師 [1]"}], ensure_ascii=False)


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    for k in ("JOB_RAG_ACCESS_CODE", "JOB_RAG_ANSWER_LIMIT", "JOB_RAG_FAKE_ANSWER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    return appmod


@pytest.fixture
def queries(web, monkeypatch):
    """記下真正拿去檢索的問句。"""
    seen, real = [], web.search
    monkeypatch.setattr(web, "search", lambda q, **kw: seen.append(q) or real(q, **kw))
    return seen


def test_follow_up_search_is_completed_and_company_comes_from_the_previous_question(web, queries):
    d = web.app.test_client().get("/api/search", query_string={"q": "那薪水呢？", "history": HIST}).get_json()
    assert queries == ["甲科技有哪些職缺？ 那薪水呢？"]
    assert d["expanded"] is True and d["company"] == "甲科技" and d["detected"] is True
    assert {h["company"] for h in d["hits"]} == {"甲科技"}


def test_without_history_or_with_company_in_question_nothing_is_completed(web, queries):
    c = web.app.test_client()
    d = c.get("/api/search", query_string={"q": "那薪水呢？"}).get_json()
    e = c.get("/api/search", query_string={"q": "乙資訊的薪水呢？", "history": HIST}).get_json()
    assert queries == ["那薪水呢？", "乙資訊的薪水呢？"] and d["expanded"] is False and e["expanded"] is False


def test_answer_endpoint_completes_the_query_and_sends_history_to_deepseek(web, queries, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    d = web.app.test_client().get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": HIST}).get_json()
    assert d["status"] == "ok" and queries == ["甲科技有哪些職缺？ 那薪水呢？"]
    sent = post.calls[0][2]["messages"][1]["content"]
    assert "先前對話" in sent and "問：甲科技有哪些職缺？" in sent and sent.rstrip().endswith("問題：那薪水呢？")


def test_history_is_not_stored_on_the_server(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = web.app.test_client()
    c.get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": HIST})
    c.get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技"})  # 同一個客戶端、這次沒帶
    assert "先前對話" not in post.calls[1][2]["messages"][1]["content"] and "徵後端工程師" not in json.dumps(post.calls[1][2], ensure_ascii=False)


@pytest.mark.parametrize("path", ["/api/search", "/api/answer", "/answer"])
@pytest.mark.parametrize("bad", ["not json", json.dumps({"q": "x"}), json.dumps([{"q": 1, "a": "y"}]), "x" * 5000])
def test_bad_history_is_a_json_400_and_never_reaches_deepseek(web, monkeypatch, path, bad):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    r = web.app.test_client().get(path, query_string={"q": "那薪水呢？", "history": bad})
    assert r.status_code == 400 and r.mimetype == "application/json" and r.get_json()["status"] == "error"
    assert "對話記錄" in r.get_json()["message"] and post.calls == [] and len(web._limiter.stamps) == 0


def test_oversized_history_turns_are_cut_before_the_prompt(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    big = json.dumps([{"q": f"問{i}", "a": "答" * 1000} for i in range(3)], ensure_ascii=False)
    assert len(big) < 4000
    web.app.test_client().get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": big})
    sent = post.calls[0][2]["messages"][1]["content"]
    assert "問：問0" not in sent and "問：問1" in sent and "問：問2" in sent  # 只留最近 2 輪
    assert "答" * 301 not in sent and sent.count("答" * 300) == 2             # 每則答案截到 300 字


def test_history_does_not_change_the_low_score_rule_or_the_limit(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    r = web.app.test_client().get("/api/answer", query_string={"q": "那薪水呢？", "history": HIST})
    assert r.get_json() == {"status": "low"} and post.calls == [] and len(web._limiter.stamps) == 0
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.0)
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "1")
    c = web.app.test_client()
    assert c.get("/api/answer", query_string={"q": "那薪水呢？", "history": HIST}).get_json()["status"] == "ok"
    assert c.get("/api/answer", query_string={"q": "那薪水呢？", "history": HIST}).status_code == 429


def test_private_text_still_never_reaches_deepseek_with_history(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    web.app.test_client().get("/api/answer", query_string={"q": "離職率 珊瑚礁 刺蝟密語？", "history": HIST})
    sent = json.dumps(post.calls[0][2], ensure_ascii=False).replace("離職率 珊瑚礁 刺蝟密語", "")
    assert not any(w in sent for w in ("離職率", "珊瑚礁", "刺蝟密語", "企鵝密語"))

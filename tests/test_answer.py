"""整理成答案：只測 answer() 與 Flask 頁面的外部行為。HTTP 用替身，不呼叫真 API。"""
import json
import urllib.error
from pathlib import Path

import pytest

from job_rag import search
from job_rag.answer import AnswerError, answer

MINI = Path(__file__).parent / "fixtures" / "mini"
PUB = {"company": "甲科技", "file": "01_甲科技.md", "heading_path": "基本資料", "private": False, "text": "公開事實ABC"}
PRIV = {"company": "乙資訊", "file": "02_乙資訊.md", "heading_path": "面試", "private": True, "text": "私人秘密XYZ"}


class FakePost:
    def __init__(self, reply="答案 [1]", exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        if self.exc:
            raise self.exc
        return {"choices": [{"message": {"content": self.reply}}]}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)


def sent_text(post):
    return json.dumps(post.calls[0][2], ensure_ascii=False)


def test_answer_has_sources_and_request_shape():
    post = FakePost()
    r = answer("問題", [PUB], post=post)
    assert r["answer"] == "答案 [1]"
    assert r["sources"] == [{"company": "甲科技", "file": "01_甲科技.md", "heading_path": "基本資料"}]
    url, headers, body, timeout = post.calls[0]
    assert url == "https://api.deepseek.com/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert body["model"] == "deepseek-flash" and timeout > 0
    assert "公開事實ABC" in sent_text(post)


def test_private_hits_never_sent_even_mixed():
    post = FakePost()
    r = answer("問題", [PRIV, PUB], post=post)
    assert "私人秘密XYZ" not in sent_text(post) and "乙資訊" not in sent_text(post)
    assert [s["company"] for s in r["sources"]] == ["甲科技"]


def test_query_mode_real_search_sends_no_private():
    hits = search("刺蝟密語 FastAPI 面試 風險", mode="query", corpus=MINI, k=50)
    assert any(h["private"] for h in hits) and any(not h["private"] for h in hits)
    post = FakePost()
    answer("刺蝟密語 FastAPI", hits, post=post)
    sent = sent_text(post)
    for h in hits:
        if h["private"]:
            assert h["text"] not in sent


def test_only_private_means_not_found_without_calling_api():
    post = FakePost()
    assert answer("問題", [PRIV], post=post) == {"answer": "查無", "sources": []}
    assert answer("問題", [], post=post)["answer"] == "查無"
    assert post.calls == []


def test_model_replying_not_found_has_no_sources():
    assert answer("問題", [PUB], post=FakePost(reply="查無"))["sources"] == []


@pytest.mark.parametrize("exc", [
    TimeoutError("t"), urllib.error.URLError("offline"),
    urllib.error.HTTPError("u", 401, "Unauthorized", {}, None),
    urllib.error.HTTPError("u", 402, "Insufficient Balance", {}, None),
])
def test_api_failure_raises_clear_error(exc):
    with pytest.raises(AnswerError):
        answer("問題", [PUB], post=FakePost(exc=exc))


def test_missing_key_raises_and_does_not_call(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    post = FakePost()
    with pytest.raises(AnswerError, match="DEEPSEEK_API_KEY"):
        answer("問題", [PUB], post=post, env_file="nonexistent.env")
    assert post.calls == []


def test_malformed_response_raises():
    def bad(*a):
        return {"oops": 1}
    with pytest.raises(AnswerError):
        answer("問題", [PUB], post=bad)


def test_model_configurable(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "other-model")
    post = FakePost()
    answer("問題", [PUB], post=post)
    assert post.calls[0][2]["model"] == "other-model"


def test_key_read_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    f = tmp_path / ".env"
    f.write_text('DEEPSEEK_API_KEY="sk-file"\n', encoding="utf-8")
    post = FakePost()
    answer("問題", [PUB], post=post, env_file=f)
    assert post.calls[0][1]["Authorization"] == "Bearer sk-file"


# ---- 頁面 ----
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    import app as appmod
    return appmod, appmod.app.test_client()


def test_page_no_api_call_until_button(client, monkeypatch):
    appmod, c = client
    post = FakePost()
    monkeypatch.setattr(appmod, "_post", post)
    html = c.get("/?q=鯨魚追蹤軟體").get_data(as_text=True)
    assert "整理成答案" in html and post.calls == []
    html = c.get("/?q=鯨魚追蹤軟體&answer=1").get_data(as_text=True)
    assert "答案 [1]" in html and len(post.calls) == 1


def test_page_private_only_has_no_button_and_no_call(client, monkeypatch):
    appmod, c = client
    post = FakePost()
    monkeypatch.setattr(appmod, "_post", post)
    html = c.get("/?q=刺蝟密語&mode=query").get_data(as_text=True)
    assert "刺蝟密語" in html and "整理成答案" not in html
    c.get("/?q=刺蝟密語&mode=query&answer=1")
    assert post.calls == []


def test_page_error_keeps_original_results(client, monkeypatch):
    appmod, c = client
    monkeypatch.setattr(appmod, "_post", FakePost(exc=TimeoutError("t")))
    html = c.get("/?q=鯨魚追蹤軟體&answer=1").get_data(as_text=True)
    assert "鯨魚" in html and "整理失敗" in html and "答案 [1]" not in html

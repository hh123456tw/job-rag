"""整理成答案：只測 answer() 與 Flask 頁面的外部行為。HTTP 用替身，不呼叫真 API。"""
import json
import urllib.error
from pathlib import Path

import pytest

from job_rag import search
from job_rag.answer import AnswerError, answer

MINI = Path(__file__).parent / "fixtures" / "mini"
PUB = {"company": "甲科技", "file": "01_甲科技.md", "heading_path": "基本資料", "text": "公開事實ABC"}


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


def test_real_search_sends_only_public_segments():
    hits = search("刺蝟密語 FastAPI 面試 風險", corpus=MINI, k=50, method="bm25")
    assert hits
    post = FakePost()
    answer("FastAPI 是什麼", hits, post=post)
    sent = sent_text(post)
    assert "刺蝟密語" not in sent and "珊瑚礁" not in sent and "離職率" not in sent


def test_no_hits_means_not_found_without_calling_api():
    post = FakePost()
    assert answer("問題", [], post=post) == {"answer": "查無", "sources": []}
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


# ---- 頁面（預設 bge-m3，用假嵌入器）----
from tests.test_vector import fake_env  # noqa: F401,E402
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


def test_page_never_shows_excluded_text_even_when_asked_for_it(client, monkeypatch):
    appmod, c = client
    post = FakePost()
    monkeypatch.setattr(appmod, "_post", post)
    for url in ("/?q=離職率 珊瑚礁 企鵝密語", "/?q=離職率 珊瑚礁&mode=query", "/?q=離職率 珊瑚礁&mode=query&answer=1"):
        html = c.get(url).get_data(as_text=True)
        body = html.split("</form>", 1)[1]  # 表單會回顯問題，只看結果區
        assert not any(w in body for w in ("離職率", "珊瑚礁", "企鵝密語", "刺蝟密語")), url
    assert post.calls  # answer=1 的那次有送出；內容只有公開段落（見 test_real_search_sends_only_public_segments）


def test_page_has_no_mode_switch_or_banner(client):
    _, c = client
    html = c.get("/?q=鯨魚追蹤軟體&mode=query").get_data(as_text=True)
    assert "鯨魚" in html
    for gone in ("查詢模式", "e8710a", "私人", "name=mode"):
        assert gone not in html, gone


def test_page_error_keeps_original_results(client, monkeypatch):
    appmod, c = client
    monkeypatch.setattr(appmod, "_post", FakePost(exc=TimeoutError("t")))
    html = c.get("/?q=鯨魚追蹤軟體&answer=1").get_data(as_text=True)
    assert "鯨魚" in html and "整理失敗" in html and "答案 [1]" not in html


def test_page_found_has_no_not_found_text(client):
    appmod, c = client
    html = c.get("/?q=鯨魚追蹤軟體").get_data(as_text=True)
    assert "可能沒有答案" not in html and "class='hit'" in html

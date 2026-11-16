"""票 21：答案優先、兩步到答案。/answer 端點（成功、失敗、逾時、用量上限、低分）與各畫面結構。DeepSeek 一律用替身。"""
import re
import urllib.error

import pytest

from job_rag import guard, retrieval
from tests.test_answer import FakePost, MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

Q = "鯨魚追蹤軟體"


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    monkeypatch.delenv("JOB_RAG_ACCESS_CODE", raising=False)
    monkeypatch.delenv("JOB_RAG_ANSWER_LIMIT", raising=False)
    monkeypatch.delenv("JOB_RAG_FAKE_ANSWER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    return appmod


def get_answer(web, post, **qs):
    web._post = post
    return web.app.test_client().get("/answer", query_string={"q": Q, **qs})


# ---- /answer：五種情況 ----
def test_answer_endpoint_success_returns_answer_and_sources(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    r = web.app.test_client().get("/answer", query_string={"q": Q})
    d = r.get_json()
    assert r.status_code == 200 and d["status"] == "ok" and d["answer"] == "答案 [1]"
    assert d["sources"] and {"company", "file", "heading_path"} <= set(d["sources"][0])
    assert len(post.calls) == 1


def test_answer_endpoint_api_failure_says_why_and_keeps_raw_usable(web, monkeypatch):
    monkeypatch.setattr(web, "_post", FakePost(exc=urllib.error.HTTPError("u", 402, "x", {}, None)))
    r = web.app.test_client().get("/answer", query_string={"q": Q})
    d = r.get_json()
    assert r.status_code == 502 and d["status"] == "error" and "餘額不足" in d["message"] and "原文" in d["message"]
    assert "answer" not in d  # 失敗時沒有假答案


def test_answer_endpoint_timeout_and_offline_are_clear_errors(web, monkeypatch):
    monkeypatch.setattr(web, "_post", FakePost(exc=TimeoutError("t")))
    d = web.app.test_client().get("/answer", query_string={"q": Q}).get_json()
    assert d["status"] == "error" and "無法連到 DeepSeek（逾時或無網路）" in d["message"]


def test_answer_endpoint_missing_key_is_error_not_fake_answer(web, monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.chdir(tmp_path)  # 沒有 .env
    d = web.app.test_client().get("/answer", query_string={"q": Q}).get_json()
    assert d["status"] == "error" and "DEEPSEEK_API_KEY" in d["message"]


def test_answer_endpoint_limit_counts_auto_loads_and_stops_calls(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "2")
    c = web.app.test_client()
    assert [c.get("/answer", query_string={"q": Q}).status_code for _ in range(2)] == [200, 200]
    r = c.get("/answer", query_string={"q": Q})
    d = r.get_json()
    assert r.status_code == 429 and d["status"] == "limit" and "上限" in d["message"] and "原文" in d["message"]
    assert len(post.calls) == 2


def test_answer_endpoint_low_score_never_calls_api_or_counts(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "1")
    c = web.app.test_client()
    for _ in range(3):
        d = c.get("/answer", query_string={"q": Q}).get_json()
        assert d["status"] == "low" and "answer" not in d
    assert post.calls == [] and len(web._limiter.stamps) == 0


def test_answer_endpoint_empty_question_is_400(web):
    assert web.app.test_client().get("/answer").status_code == 400


def test_answer_endpoint_company_filter_applies(web, monkeypatch):
    monkeypatch.setattr(web, "_post", FakePost())
    d = web.app.test_client().get("/answer", query_string={"q": Q, "company": "乙資訊"}).get_json()
    assert {s["company"] for s in d["sources"]} == {"乙資訊"}


def test_answer_endpoint_is_behind_access_code_and_never_sends_private_text(web, monkeypatch):
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", "abc-123")
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = web.app.test_client()
    assert c.get("/answer", query_string={"q": Q}).status_code == 403 and post.calls == []
    r = c.get("/answer", query_string={"q": Q, "k": "abc-123"})
    assert r.status_code == 200
    sent = str(post.calls[0][2])
    assert not any(w in sent for w in ("離職率", "珊瑚礁", "企鵝密語", "刺蝟密語"))


# ---- 開發用替身旗標：預設關 ----
def test_fake_answer_flag_is_off_by_default_and_uses_real_post(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    web.app.test_client().get("/answer", query_string={"q": Q})
    assert len(post.calls) == 1  # 沒設旗標：走（被測試換掉的）真 _post 路徑


@pytest.mark.parametrize("mode,status,key", [("ok", "ok", "answer"), ("fail", "error", "message")])
def test_fake_answer_flag_replaces_deepseek_only_when_set(web, monkeypatch, mode, status, key):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    monkeypatch.setenv("JOB_RAG_FAKE_ANSWER", mode)
    d = web.app.test_client().get("/answer", query_string={"q": Q}).get_json()
    assert d["status"] == status and key in d and post.calls == []


def test_fake_answer_flag_is_not_set_by_launchers_or_docs_as_default():
    from pathlib import Path
    root = Path(__file__).parent.parent
    for f in ("start.bat", "start_phone.bat", "start_public.bat", "scripts/start_public.ps1"):
        assert "FAKE_ANSWER" not in (root / f).read_text(encoding="utf-8"), f


# ---- 結果頁：原文先出現，答案在背景載入 ----
def result(web, url=f"/?q={Q}"):
    return web.app.test_client().get(url).get_data(as_text=True)


def test_result_page_renders_raw_text_and_loading_card_without_calling_deepseek(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    html = result(web)
    assert post.calls == []  # 伺服器不在頁面請求裡等 DeepSeek
    assert "鯨魚" in html and "class='hit'" in html  # 原文立刻可見
    assert re.search(r"<section id=answer[^>]*data-q=", html) and "整理中" in html
    assert html.index("id=answer") < html.index("<details id=raw")  # 答案卡在原文上面
    assert ">看原文<" in html


def test_raw_details_starts_open_and_script_collapses_it_so_no_js_still_shows_raw(web):
    html = result(web)
    assert re.search(r"<details id=raw open>", html)  # 沒有 JS 時原文是展開的
    assert "<noscript>" in html and "answer=1" in html.split("<noscript>", 1)[1].split("</noscript>", 1)[0]  # 沒有 JS：舊按鈕（連結）
    assert html.count("<script>") == 1 and "src=" not in html.split("<script>", 1)[1].split("</script>", 1)[0]


def test_script_handles_every_failure_by_opening_raw_and_uses_text_not_html(web):
    js = result(web).split("<script>", 1)[1].split("</script>", 1)[0]
    assert "fetch(" in js and "AbortController" in js  # 逾時
    assert ".open=true" in js.replace(" ", "")  # 失敗時展開原文
    assert "innerHTML" not in js  # 答案文字用 textContent，不當 HTML
    assert "catch" in js


def test_low_score_page_has_no_loading_card_no_script_and_open_dim_raw(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    html = result(web)
    assert "可能沒有答案" in html and "class='hit dim'" in html and re.search(r"<details id=raw open>", html)
    assert "id=answer" not in html and "<script" not in html and "整理成答案" not in html
    assert post.calls == []


def test_server_side_answer_still_works_without_js(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    html = result(web, f"/?q={Q}&answer=1")
    assert "答案 [1]" in html and len(post.calls) == 1 and "<script" not in html


def test_result_page_keeps_company_and_has_two_back_links(web):
    html = result(web, "/?faq=what&company=乙資訊")
    assert "乙資訊是做什麼的？" in html and "<b>乙資訊</b>" in html
    assert 'href="/c/%E4%B9%99%E8%B3%87%E8%A8%8A">← 換問題<' in html
    assert 'href="/">← 公司清單<' in html
    assert "data-company=\"乙資訊\"" in html


def test_cross_company_result_page_has_single_back_link(web):
    html = result(web)
    assert 'href="/">← 換問題<' in html and "← 公司清單" not in html


# ---- 沒有 JS 的伺服器渲染退路（公司頁在 /?company=）----
def test_company_screen_fallback_shows_company_four_questions_and_back(web):
    html = result(web, "/?company=乙資訊")
    assert "<h1>乙資訊</h1>" in html and 'href="/">← 公司清單<' in html
    assert len(re.findall(r"name=faq value=", html)) == 4
    assert re.search(r'<input type=hidden name=company value="乙資訊">', html)
    assert "class='hit" not in html  # 還沒問，沒有結果


def test_company_screen_faq_button_is_a_single_submit_that_keeps_company(web):
    html = web.app.test_client().get("/?faq=jobs&company=乙資訊").get_data(as_text=True)
    assert "乙資訊有哪些職缺？" in html and "id=answer" in html


# ---- 排版 ----
def css(web):
    return re.search(r"<style>(.*?)</style>", result(web, "/"), re.S).group(1)


def test_phone_type_and_touch_targets(web):
    s = css(web)
    assert re.search(r"body\{font:17px", s)
    for sel in ("button", "input", "summary", "nav a"):
        m = re.search(r"(?:^|[,}\n])" + re.escape(sel) + r"[^{]*\{[^}]*min-height:(\d+)px", s)
        assert m and int(m.group(1)) >= 48, sel


def test_no_external_resources_in_new_screens(web):
    for u in ("/", "/c/乙資訊", f"/?q={Q}"):
        html = result(web, u)
        assert not re.search(r"(src|href)=[\"']?(https?:)?//", html) and "@import" not in html and "<img" not in html, u

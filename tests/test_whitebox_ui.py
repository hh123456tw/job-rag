"""票 28：白盒化畫面。用 Playwright 驅動系統 Chrome 打開本機測試伺服器（假嵌入器、DeepSeek 替身）。
替身的 usage（1234／56）是假值，只驗證畫面會顯示；沒有 Chrome 或 Playwright 時整檔略過。"""
import threading
from urllib.parse import quote

import pytest

from job_rag import guard, retrieval, search
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

sync_api = pytest.importorskip("playwright.sync_api")
Q = "鯨魚追蹤軟體"
PAGE = "/c/" + quote("全部公司")


@pytest.fixture
def live(monkeypatch):
    from werkzeug.serving import make_server
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    for k in ("JOB_RAG_ACCESS_CODE", "JOB_RAG_ANSWER_LIMIT", "JOB_RAG_OWNER_PIN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JOB_RAG_FAKE_ANSWER", "usage")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")  # 假的
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    srv = make_server("127.0.0.1", 0, appmod.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def page(live):
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"沒有可用的 Chrome：{e}")
        pg = b.new_page()
        pg.goto(live + PAGE)
        yield pg
        b.close()


def ask(pg, q=Q):
    pg.fill("#qi", q)
    pg.click("#bar .go")
    pg.wait_for_selector(".msg.bot .chips >> nth=-1")  # 一輪結束（done 會放常用題按鈕）


def scores(question=Q):
    return [h["score"] for h in search(question, corpus=MINI, gate=False, dedupe=True)]


def mid_threshold(monkeypatch):
    """把門檻設在第 1 與第 2 段分數之間：第 1 段高於、之後低於。"""
    s = scores()
    assert s[0] > s[1]
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", (s[0] + s[1]) / 2)
    return s


def test_every_hit_shows_its_score_and_threshold_and_marks_low_ones(page, monkeypatch):
    s = mid_threshold(monkeypatch)
    thr = retrieval.NOT_FOUND_THRESHOLD
    ask(page)
    tags = page.locator(".hit .sc")
    assert tags.count() == len(s)
    first = tags.nth(0).text_content()
    assert f"{s[0]:.3f}" in first and f"{thr:.3f}" in first and "≥" in first and "低於門檻" not in first
    assert "低於門檻" in tags.nth(1).text_content() and "<" in tags.nth(1).text_content()
    assert page.locator(".hit").nth(0).get_attribute("class") == "hit"  # 高於門檻的不淡色
    assert "dim" in page.locator(".hit").nth(1).get_attribute("class")


def test_score_exactly_at_threshold_counts_as_above(page, monkeypatch):
    s = scores()
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", s[0])
    ask(page)
    t = page.locator(".hit .sc").nth(0)
    assert "≥" in t.text_content() and "低於" not in t.text_content()


def test_no_score_label_when_server_sends_no_score(page):
    page.route("**/api/search*", lambda r: r.fulfill(json={"status": "ok", "company": "", "detected": False, "expanded": False,
                                                           "hits": [{"company": "甲", "file": "f", "heading_path": "h", "text": "t"}]}))
    ask(page)
    assert page.locator(".hit").count() == 1 and page.locator(".sc").count() == 0


# ---- 可點引用 ----
def answer_route(pg, text):
    top = search(Q, corpus=MINI, gate=False, dedupe=True)[1]  # 故意取第 2 段，確認對到的不是第 1 段
    sources = [{k: top[k] for k in ("company", "file", "heading_path")}]
    pg.route("**/api/answer*", lambda r: r.fulfill(json={"status": "ok", "answer": text, "sources": sources}))


def test_citation_numbers_become_buttons_that_open_and_flag_the_right_hit(page):
    answer_route(page, "先 [1] 再 [2]，其他 [9] 與 [0] 不是段落。")
    ask(page)
    cites = page.locator(".answer .cite")
    assert cites.count() == 2 and [cites.nth(i).text_content() for i in range(2)] == ["[1]", "[2]"]
    assert page.locator(".answer").text_content() == "先 [1] 再 [2]，其他 [9] 與 [0] 不是段落。"  # [9]、[0] 維持純文字
    assert not page.locator("details.raw").evaluate("d => d.open")
    cites.nth(1).click()
    assert page.locator("details.raw").evaluate("d => d.open")
    assert "flash" in page.locator(".hit").nth(1).get_attribute("class")
    assert "flash" not in page.locator(".hit").nth(0).get_attribute("class")
    page.wait_for_function("() => !document.querySelector('.hit.flash')")  # 短暫標示後移除


def test_source_label_is_clickable_and_points_to_matching_hit(page):
    answer_route(page, "答案 [1]")
    ask(page)
    src = page.locator(".src .cite")
    assert src.count() == 1
    n = src.get_attribute("data-n")
    assert n == "2"
    src.click()
    assert "flash" in page.locator(".hit").nth(int(n) - 1).get_attribute("class")


def test_hostile_answer_text_is_inert(page):
    answer_route(page, "<img src=x onerror=\"window.__pwn=1\"><script>window.__pwn=1</script> [1]")
    ask(page)
    assert page.locator(".answer img, .answer script").count() == 0
    assert page.evaluate("window.__pwn") is None
    assert "<img" in page.locator(".answer").text_content()


def test_citations_survive_reload_of_saved_chat(page):
    answer_route(page, "答案 [1]")
    ask(page)
    page.reload()
    page.locator(".answer .cite").click()  # 事件委派：還原的 innerHTML 也能點
    assert page.locator("details.raw").evaluate("d => d.open")


# ---- 耗時與用量列（替身 usage 是假值 1234／56）----
def test_meta_line_shows_search_answer_time_and_fake_usage(page):
    ask(page)
    t = page.locator(".steps .meta").text_content()
    assert t.startswith("檢索 ") and "｜整理 " in t and t.endswith("｜輸入 1234／輸出 56 tokens")


def test_meta_line_omits_missing_fields_and_never_invents_numbers(page):
    page.unroute_all()
    page.route("**/api/answer*", lambda r: r.fulfill(json={"status": "ok", "answer": "答案", "sources": []}))
    ask(page)
    t = page.locator(".steps .meta").text_content()
    assert "token" not in t and "整理" not in t and t.startswith("檢索 ")  # 缺 answer_ms、usage 就不顯示


def test_meta_line_absent_when_nothing_is_known(page):
    page.route("**/api/search*", lambda r: r.fulfill(json={"status": "error", "message": "壞了"}))
    ask(page)
    assert page.locator(".meta").count() == 0


def test_meta_partial_usage_shows_only_the_known_side(page):
    page.route("**/api/answer*", lambda r: r.fulfill(json={"status": "ok", "answer": "答案", "sources": [],
                                                           "answer_ms": 1500, "usage": {"completion_tokens": 9}}))
    ask(page)
    assert page.locator(".steps .meta").text_content().endswith("整理 1.50 秒｜輸出 9 tokens")

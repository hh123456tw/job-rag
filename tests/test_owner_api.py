"""票 24：自用／展示切換的 HTTP 行為。混合語料（公開＋私人段落＋面經）；DeepSeek 一律用替身，密碼與金鑰都是假的。
重點：沒有有效的本人 cookie，任何入口（查詢參數、cookie 被改、history、直接打 API、公司頁、/about）都查不到私人資料。"""
import json

import pytest

from job_rag import guard, owner, retrieval
from job_rag.owner import COOKIE, Owner
from tests.test_answer import FakePost
from tests.test_modes import IV, SECRET, PRIVATE_MD, PUBLIC_MD, _write
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

PIN = "fake-owner-pin-for-tests"
SELF_HIST = json.dumps([{"q": f"{SECRET}是什麼？", "a": f"{SECRET} 的答案", "m": "self"}], ensure_ascii=False)


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def web(monkeypatch, tmp_path, clock):
    corpus = _write(tmp_path / "mixed", PUBLIC_MD + PRIVATE_MD)
    sd = tmp_path / "selfdata" / "面經" / "goodjob"
    sd.mkdir(parents=True)
    row = {"source": "goodjob.life", "company": "甲科技", "interview_time": "2024-05", "job_title": "後端", "locked": False,
           "window_ok": True, "sections": [{"subtitle": "面試過程", "content": f"{IV} 問了資料庫。"}], "interview_qas": []}
    (sd / "甲科技.jsonl").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("JOB_RAG_SELF_DIR", str(tmp_path / "selfdata"))
    monkeypatch.setenv("JOB_RAG_CORPUS", str(corpus))
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    for k in ("JOB_RAG_ACCESS_CODE", "JOB_RAG_FAKE_ANSWER", "JOB_RAG_ANSWER_LIMIT"):
        monkeypatch.delenv(k, raising=False)
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    monkeypatch.setattr(appmod, "_owner", Owner(clock=clock))
    monkeypatch.setattr(appmod, "LIVE_COMPANIES", [("甲科技", "甲科技"), ("乙資訊", "乙資訊")])
    return appmod


def login(client, pin=PIN):
    return client.post("/api/owner/login", json={"pin": pin})


def as_owner(web):
    c = web.app.test_client()
    assert login(c).status_code == 200
    return c


# ---- 密碼與 cookie ----
def test_wrong_pin_is_401_without_cookie_and_right_pin_sets_a_hardened_cookie(web):
    c = web.app.test_client()
    r = login(c, "wrong")
    assert r.status_code == 401 and "Set-Cookie" not in r.headers and PIN not in r.get_data(as_text=True)
    r = login(c)
    cookie = r.headers["Set-Cookie"]
    assert r.status_code == 200 and cookie.startswith(COOKIE + "=") and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Max-Age=28800" in cookie and "Secure" not in cookie and PIN not in cookie


def test_cookie_is_secure_over_https(web):
    r = web.app.test_client().post("/api/owner/login", json={"pin": PIN}, headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in r.headers["Set-Cookie"]


def test_pin_in_url_or_form_is_never_accepted(web):
    c = web.app.test_client()
    assert c.post("/api/owner/login?pin=" + PIN).status_code == 400
    assert c.post("/api/owner/login", data={"pin": PIN}).status_code == 400
    assert c.get("/api/owner/login?pin=" + PIN).status_code == 405
    assert c.get("/c/甲科技").status_code == 200 and SECRET not in c.get(f"/api/search?q={SECRET}&pin={PIN}").get_data(as_text=True)


def test_five_wrong_pins_then_429_even_for_the_right_one_until_the_window_passes(web, clock):
    c = web.app.test_client()
    for _ in range(5):
        assert login(c, "x").status_code == 401
    assert login(c).status_code == 429
    assert login(web.app.test_client()).status_code == 429  # 全域計數：換一個客戶端也一樣
    clock.t += 601
    assert login(c).status_code == 200


def test_logout_returns_to_demo_immediately(web):
    c = as_owner(web)
    assert SECRET in json.dumps(c.get("/api/search", query_string={"q": SECRET}).get_json(), ensure_ascii=False)
    assert c.post("/api/owner/logout").status_code == 200
    assert SECRET not in json.dumps(c.get("/api/search", query_string={"q": SECRET}).get_json(), ensure_ascii=False)


def test_without_owner_password_there_is_no_owner_mode_and_pages_are_unchanged(web, monkeypatch):
    monkeypatch.delenv("JOB_RAG_OWNER_PIN")
    c = web.app.test_client()
    assert login(c).status_code == 404 and c.post("/api/owner/logout").status_code == 404
    for path in ("/", "/c/甲科技"):
        html = c.get(path).get_data(as_text=True)
        assert "id=modebar" not in html and "class=selfbar" not in html and "/api/owner" not in html
    d = c.get("/api/search", query_string={"q": "貓熊"}).get_json()
    assert "mode" not in d and "Vary" not in c.get("/").headers


def test_access_code_still_guards_the_login_endpoint(web, monkeypatch):
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", "fake-code")
    r = web.app.test_client().post("/api/owner/login", json={"pin": PIN})
    assert r.status_code == 403 and r.is_json


# ---- 展示模式零洩漏 ----
MARKERS = ("要問薪資", "出差多", "第二關是主管", "問了資料庫", "面經（GoodJob）")  # 私人內文；不含查詢字串本身（頁面會回顯使用者輸入的問句）


def leak(text):
    return any(m in text for m in MARKERS)


def all_entrances(c):
    """展示模式下所有會回內容的入口，每個都帶上各種想要偷看私人資料的參數。回傳全部回應文字。"""
    out = []
    for qs in ({"mode": "self"}, {"mode": "SELF"}, {"self": "1"}, {"owner": "1"}, {"pin": PIN}, {"history": SELF_HIST}, {"history": SELF_HIST.replace("self", "demo")}):
        for path in ("/api/search", "/api/answer", "/answer"):
            out.append(c.get(path, query_string={"q": SECRET, "company": "甲科技"} | qs).get_data(as_text=True))
            out.append(c.get(path, query_string={"q": IV} | qs).get_data(as_text=True))
        out.append(c.get("/", query_string={"q": SECRET, "answer": 1} | qs).get_data(as_text=True))
        out.append(c.get("/", query_string={"q": IV, "company": "甲科技"} | qs).get_data(as_text=True))
        out.append(c.get("/c/甲科技", query_string=qs).get_data(as_text=True))
    out += [c.get(p).get_data(as_text=True) for p in ("/", "/c/甲科技", "/c/全部公司", "/about", "/about?all=1")]
    return out


def test_demo_has_no_private_data_anywhere_for_a_visitor_with_no_cookie(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    assert not any(leak(t) for t in all_entrances(web.app.test_client()))
    assert not leak(json.dumps(post.calls, ensure_ascii=False))  # 送給 DeepSeek 的內容也沒有


@pytest.mark.parametrize("cookie", ["", "garbage", "1.2.3", "99999999999.abcd.deadbeef", "é.é.é", "a" * 5000])
def test_tampered_or_forged_cookie_is_demo(web, monkeypatch, cookie):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = web.app.test_client()
    c.set_cookie(COOKIE, cookie)
    assert not any(leak(t) for t in all_entrances(c))
    assert not leak(json.dumps(post.calls, ensure_ascii=False))
    assert "class=selfbar" not in c.get("/").get_data(as_text=True)


def test_expired_cookie_and_cookie_from_a_restarted_server_are_demo(web, clock, monkeypatch):
    c = as_owner(web)
    assert SECRET in json.dumps(c.get("/api/search", query_string={"q": SECRET}).get_json(), ensure_ascii=False)
    clock.t += 8 * 3600 + 1
    assert not any(leak(t) for t in all_entrances(c))
    clock.t = 1000.0
    monkeypatch.setattr(web, "_owner", Owner(clock=clock))  # 重啟：新金鑰
    assert not any(leak(t) for t in all_entrances(c))


def test_demo_deepseek_prompt_has_only_public_segments_on_mixed_corpus(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = web.app.test_client()
    d = c.get("/api/answer", query_string={"q": "甲科技做什麼 貓熊 職缺", "company": "甲科技"}).get_json()
    assert d["status"] == "ok" and post.calls
    sent = json.dumps(post.calls[0][2], ensure_ascii=False)
    assert "貓熊" in sent and not leak(sent)


def test_demo_drops_history_that_is_not_marked_demo(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = web.app.test_client()
    seen = []
    real = web.search
    monkeypatch.setattr(web, "search", lambda q, **kw: seen.append((q, kw.get("mode"))) or real(q, **kw))
    untagged = json.dumps([{"q": f"{SECRET}是什麼？", "a": f"{SECRET} 答案"}], ensure_ascii=False)
    for h in (SELF_HIST, untagged, SELF_HIST.replace('"self"', '"demo "'), SELF_HIST.replace('"self"', "null")):
        r = c.get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": h})
        assert r.status_code == 200  # 丟掉，不報錯
    assert all(q == "那薪水呢？" and m == "demo" for q, m in seen)  # 沒有被補全成私人問句
    assert not leak(json.dumps(post.calls, ensure_ascii=False))
    # 負向對照：標記為展示的輪次照常使用
    ok = json.dumps([{"q": "甲科技有哪些職缺？", "a": "徵後端工程師 [1]", "m": "demo"}], ensure_ascii=False)
    c.get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": ok})
    assert "先前對話" in post.calls[-1][2]["messages"][1]["content"]


# ---- 自用模式 ----
def test_owner_finds_private_notes_and_interviews_and_sends_them_to_deepseek(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = as_owner(web)
    d = c.get("/api/search", query_string={"q": IV, "company": "甲科技"}).get_json()
    assert d["mode"] == "self" and any(IV in h["text"] and h["private"] for h in d["hits"])
    a = c.get("/api/answer", query_string={"q": f"{SECRET} 要問什麼", "company": "甲科技"}).get_json()
    assert a["status"] == "ok" and a["mode"] == "self" and SECRET in json.dumps(post.calls[0][2], ensure_ascii=False)
    assert leak(json.dumps(post.calls[0][2], ensure_ascii=False)) and leak(json.dumps(d, ensure_ascii=False))  # 負向對照：leak() 真的抓得到


def test_self_mode_accepts_self_history_only(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    c = as_owner(web)
    demo_h = json.dumps([{"q": "甲科技有哪些職缺？", "a": "徵後端工程師", "m": "demo"}], ensure_ascii=False)
    user = lambda: post.calls[-1][2]["messages"][1]["content"]
    c.get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": demo_h})
    assert "先前對話" not in user()
    c.get("/api/answer", query_string={"q": "那薪水呢？", "company": "甲科技", "history": SELF_HIST})
    assert "先前對話" in user()


def test_pages_show_orange_banner_toggle_and_mode_only_for_owner(web):
    demo, own = web.app.test_client(), as_owner(web)
    for path in ("/", "/c/甲科技", "/c/全部公司", "/?q=貓熊"):
        d, o = demo.get(path).get_data(as_text=True), own.get(path).get_data(as_text=True)
        assert "自用模式：資料會送到 DeepSeek，請勿給別人看" in o and "class=selfbar" not in d, path
        assert "id=modebar" in d and "id=modebar" in o and "data-mode=demo" in d and "data-mode=self" in o, path
        assert "aria-pressed=true>展示" in d and "aria-pressed=true>自用" in o, path
    assert "no-store" in own.get("/").headers["Cache-Control"] and "Cookie" in demo.get("/").headers["Vary"]
    about = own.get("/about").get_data(as_text=True)
    assert not leak(about) and "面經" not in about


def test_hint_card_in_self_mode_names_interviews_and_private_topics(web):
    import re
    import html as h
    def hint(c):
        return json.loads(h.unescape(re.search(r'data-hint="([^"]*)"', c.get("/c/甲科技").get_data(as_text=True)).group(1)))
    own, demo = hint(as_owner(web)), hint(web.app.test_client())
    line = next(x for x in own if x.startswith("自用資料"))
    assert "面經 1 篇" in line and "面談作戰卡" in line and "自用模式" in line
    assert not any("自用資料" in x or "面經" in x for x in demo)
    assert any("面試與評價" in x for x in demo) and not any("面試與評價" in x for x in own if "沒有" in x)


def test_interview_presets_only_in_self_mode_and_only_when_the_company_has_interviews(web):
    import re
    import html as h
    def presets(c, label):
        return json.loads(h.unescape(re.search(r'data-presets="([^"]*)"', c.get(f"/c/{label}").get_data(as_text=True)).group(1)))
    own, demo = as_owner(web), web.app.test_client()
    assert not any(k.startswith("iv-") for k, _, _ in presets(demo, "甲科技"))
    assert [q for k, _, q in presets(own, "甲科技") if k.startswith("iv-")] == ["甲科技面試會問什麼？", "甲科技面試流程是什麼？"]
    assert not any(k.startswith("iv-") for k, _, _ in presets(own, "乙資訊"))  # 乙資訊沒有面經
    assert any(k == "iv-all" for k, _, _ in presets(own, "全部公司"))


def test_status_header_does_not_cache_across_modes(web):
    own = as_owner(web)
    r = own.get("/api/search", query_string={"q": "貓熊"})
    assert r.get_json()["mode"] == "self" and "no-store" in r.headers["Cache-Control"]
    own.post("/api/owner/logout")
    assert own.get("/api/search", query_string={"q": "貓熊"}).get_json()["mode"] == "demo"


def test_self_index_still_loading_gives_503_not_a_leak_or_a_hang(web, monkeypatch):
    monkeypatch.setitem(web._warm, "self", "loading")
    own = as_owner(web)
    r = own.get("/api/search", query_string={"q": SECRET})
    assert r.status_code == 503 and SECRET not in r.get_data(as_text=True) and "準備中" in r.get_json()["message"]
    assert "準備中" in own.get("/c/甲科技").get_data(as_text=True)
    assert web.app.test_client().get("/api/search", query_string={"q": "貓熊"}).status_code == 200  # 展示不受影響


def test_answer_limit_and_threshold_apply_in_both_modes(web, monkeypatch):
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "1")
    monkeypatch.setattr(web, "_post", FakePost())
    own = as_owner(web)
    assert own.get("/api/answer", query_string={"q": "貓熊 職缺", "company": "甲科技"}).get_json()["status"] == "ok"
    assert own.get("/api/answer", query_string={"q": "貓熊 職缺", "company": "甲科技"}).status_code == 429
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 99)
    assert own.get("/api/answer", query_string={"q": "貓熊", "company": "甲科技"}).get_json()["status"] == "low"

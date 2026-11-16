"""票 20：公開網址前的存取碼與用量上限。只走 Flask test client 與可注入時鐘，不連任何網路。"""
from pathlib import Path

import pytest

from job_rag import guard
from tests.test_answer import FakePost, MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

ROOT = Path(__file__).parent.parent
CODE = "s3cretCode_-42"


@pytest.fixture
def appmod(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    monkeypatch.delenv("JOB_RAG_ACCESS_CODE", raising=False)
    monkeypatch.delenv("JOB_RAG_ANSWER_LIMIT", raising=False)
    import app as m
    return m


@pytest.fixture
def locked(appmod, monkeypatch):
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", CODE)
    return appmod.app.test_client()


def test_without_env_nothing_changes_and_no_cookie(appmod):
    r = appmod.app.test_client().get("/?q=鯨魚追蹤軟體")
    assert r.status_code == 200 and "Set-Cookie" not in r.headers


@pytest.mark.parametrize("path", ["/", "/about", "/?q=鯨魚追蹤軟體"])
def test_missing_code_is_403_and_does_not_leak(locked, path):
    r = locked.get(path)
    body = r.get_data(as_text=True)
    assert r.status_code == 403 and "存取碼" in body and CODE not in body
    assert "Set-Cookie" not in r.headers


@pytest.mark.parametrize("bad", ["", CODE + "x", CODE[:-1], CODE.upper(), "x" * 200, "存取碼", " " + CODE])
def test_near_miss_codes_are_blocked(locked, bad):
    assert locked.get("/", query_string={"k": bad}).status_code == 403


def test_right_code_sets_httponly_lax_cookie_then_works_without_k(locked):
    r = locked.get("/", query_string={"k": CODE})
    cookie = r.headers["Set-Cookie"]
    assert r.status_code == 200 and "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Secure" not in cookie
    assert locked.get("/about").status_code in (200, 500)  # 不再 403（about 的輸出檔缺時是 500，與存取碼無關）
    assert locked.get("/?q=鯨魚追蹤軟體").status_code == 200


def test_cookie_is_secure_behind_https_proxy(locked):
    r = locked.get("/", query_string={"k": CODE}, headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in r.headers["Set-Cookie"]


def test_wrong_cookie_is_blocked(locked):
    locked.set_cookie(guard.COOKIE, CODE + "x")
    assert locked.get("/").status_code == 403


def test_static_and_manifest_are_open_without_code(locked):
    assert locked.get("/static/icon-192.png").status_code == 200
    assert locked.get("/manifest.webmanifest").status_code == 200


def test_empty_env_value_means_no_guard(appmod, monkeypatch):
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", "")
    assert appmod.app.test_client().get("/").status_code == 200


# ---- 用量上限 ----
def test_rate_limit_sliding_window_with_injected_clock():
    t = [0.0]
    rl = guard.RateLimit(clock=lambda: t[0], window=3600)
    assert rl.try_acquire(2) == 0
    t[0] = 1000
    assert rl.try_acquire(2) == 0
    assert rl.try_acquire(2) == 2600  # 第 3 次被擋；最舊的一筆 t=0 在 t=3600 滑出
    t[0] = 3600
    assert rl.try_acquire(2) == 0  # 第一筆滑出，空出一個名額
    assert rl.try_acquire(2) == 1000  # 又滿了；最舊的是 t=1000


def test_limit_env_default_and_invalid(monkeypatch):
    monkeypatch.delenv("JOB_RAG_ANSWER_LIMIT", raising=False)
    assert guard.answer_limit() == 100
    for bad in ("abc", "0", "-3", ""):
        monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", bad)
        assert guard.answer_limit() == 100
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "2")
    assert guard.answer_limit() == 2


def test_answer_requests_over_limit_get_429_but_raw_results_and_plain_search_unaffected(appmod, monkeypatch):
    t = [0.0]
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit(clock=lambda: t[0]))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    post = FakePost()
    monkeypatch.setattr(appmod, "_post", post)
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "2")
    c = appmod.app.test_client()
    url = "/?q=鯨魚追蹤軟體&answer=1"
    assert [c.get(url).status_code for _ in range(2)] == [200, 200]
    r = c.get(url)
    html = r.get_data(as_text=True)
    assert r.status_code == 429 and "上限" in html and "鯨魚" in html and "原文結果不受影響" in html
    assert len(post.calls) == 2  # 超過後沒有再呼叫 DeepSeek
    assert c.get("/?q=鯨魚追蹤軟體").status_code == 200  # 只看原文不計次
    t[0] = 3601
    assert c.get(url).status_code == 200 and len(post.calls) == 3


# ---- 啟動檔 ----
def test_start_public_listens_locally_only_and_never_touches_secrets():
    if not (ROOT / "start_public.bat").exists():
        pytest.skip("公開版不含通道啟動檔")
    bat = (ROOT / "start_public.bat").read_text(encoding="utf-8")
    ps = (ROOT / "scripts" / "start_public.ps1").read_text(encoding="utf-8")
    both = (bat + ps).lower()
    assert "0.0.0.0" not in both and "authtoken" not in both and "deepseek_api_key" not in both and ".env" not in both
    assert "127.0.0.1" in ps and "4040/api/tunnels" in ps and "secrets" in ps and "ACCESS_CODE" in ps

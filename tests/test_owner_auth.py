"""票 24：本人密碼、嘗試次數上限、簽名 cookie。時鐘可注入。"""
import pytest

from job_rag.owner import Owner

PIN = "fake-pin-123"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


def test_no_pin_means_no_owner_mode(monkeypatch):
    monkeypatch.delenv("JOB_RAG_OWNER_PIN", raising=False)
    assert Owner().enabled is False


def test_correct_pin_issues_cookie_that_validates(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    o = Owner(clock=clock)
    r, cookie = o.login(PIN)
    assert r == "ok" and o.valid(cookie)


def test_wrong_pin_and_non_ascii_pin_are_bad_without_cookie(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    o = Owner(clock=clock)
    assert o.login("nope") == ("bad", None) and o.login("密碼") == ("bad", None) and o.login("") == ("bad", None)


def test_five_failures_in_ten_minutes_lock_even_the_right_pin(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    o = Owner(clock=clock)
    for _ in range(5):
        assert o.login("x")[0] == "bad"
    assert o.login(PIN) == ("locked", None)
    clock.t += 601  # 視窗過了就解鎖
    assert o.login(PIN)[0] == "ok"


def test_four_failures_do_not_lock(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    o = Owner(clock=clock)
    for _ in range(4):
        o.login("x")
    assert o.login(PIN)[0] == "ok"


def test_cookie_expires_after_8_hours_and_rejects_tampering_and_garbage(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    o = Owner(clock=clock)
    _, c = o.login(PIN)
    exp, nonce, sig = c.split(".")
    assert not o.valid(f"{int(exp) + 99999}.{nonce}.{sig}")  # 改效期
    assert not o.valid(f"{exp}.{nonce}.{sig[:-1]}0" if sig[-1] != "0" else f"{exp}.{nonce}.{sig[:-1]}1")
    for junk in ("", "a", "a.b", "1.2.3.4", None, "x.y.z", "é.é.é"):
        assert not o.valid(junk)
    clock.t += 8 * 3600 + 1
    assert not o.valid(c)


def test_cookie_from_another_process_secret_is_invalid(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    _, c = Owner(clock=clock).login(PIN)
    assert not Owner(clock=clock).valid(c)  # 重啟＝新金鑰


def test_valid_is_false_when_disabled(monkeypatch, clock):
    monkeypatch.setenv("JOB_RAG_OWNER_PIN", PIN)
    _, c = Owner(clock=clock).login(PIN)
    monkeypatch.delenv("JOB_RAG_OWNER_PIN")
    assert not Owner(clock=clock).valid(c)

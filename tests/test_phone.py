"""票 17：手機現場展示。預設只監聽本機；手機模式才對區網開放；偵測區網 IP；主頁網址只給本機看。"""
from pathlib import Path

import pytest

from job_rag import netinfo
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

ROOT = Path(__file__).parent.parent
# 取自一台真實筆電的網卡形態（名稱、位址）
REAL = [("乙太網路 4", "169.254.135.159"), ("VMware Network Adapter VMnet8", "192.168.227.1"),
        ("乙太網路 2", "192.168.56.1"), ("vEthernet (Default Switch)", "172.23.224.1"),
        ("藍牙網路連線", "169.254.162.8"), ("Wi-Fi", "169.254.245.27"), ("乙太網路", "192.168.0.50"),
        ("Loopback Pseudo-Interface 1", "127.0.0.1")]


def ips(found):
    return [c["ip"] for c in found]


def test_excludes_loopback_linklocal_and_virtual_adapters():
    assert ips(netinfo.lan_candidates(REAL)) == ["192.168.0.50", "192.168.56.1"]


def test_wifi_beats_wired_and_gateway_like_dot_one_goes_last():
    found = netinfo.lan_candidates([("乙太網路 2", "192.168.56.1"), ("乙太網路", "192.168.0.50"), ("Wi-Fi", "172.20.10.3")])
    assert ips(found) == ["172.20.10.3", "192.168.0.50", "192.168.56.1"]
    assert found[0]["best"] and not found[1]["best"]


def test_near_miss_names_are_kept_and_nothing_found_is_empty():
    # 「Ethernet」「Wi-Fi 2」不含虛擬網卡字樣，要留下
    assert ips(netinfo.lan_candidates([("Ethernet", "10.0.0.7"), ("Wi-Fi 2", "192.168.1.9")])) == ["192.168.1.9", "10.0.0.7"]
    assert netinfo.lan_candidates([("Wi-Fi", "169.254.1.1"), ("lo", "127.0.0.1")]) == []


def test_banner_lists_all_and_marks_best_and_handles_none():
    text = netinfo.banner(netinfo.lan_candidates(REAL), 5000)
    assert "手機請開：http://192.168.0.50:5000" in text and "http://192.168.56.1:5000" in text
    assert text.count("最可能") == 1
    none = netinfo.banner([], 5000)
    assert "找不到" in none and "http://" not in none


def test_default_host_is_loopback_and_phone_mode_needs_env(monkeypatch):
    monkeypatch.delenv("JOB_RAG_HOST", raising=False)
    assert netinfo.listen_host() == "127.0.0.1" and not netinfo.phone_mode()
    monkeypatch.setenv("JOB_RAG_HOST", "0.0.0.0")
    assert netinfo.listen_host() == "0.0.0.0" and netinfo.phone_mode()
    monkeypatch.setenv("JOB_RAG_HOST", "localhost")  # 本機別名不算手機模式
    assert not netinfo.phone_mode()


# ---- 主頁網址：只在手機模式＋來自本機 ----
@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    import app as appmod
    monkeypatch.setattr(appmod.netinfo, "detect", lambda: netinfo.lan_candidates(REAL))
    return appmod.app


def get(app, addr, path="/"):
    return app.test_client().get(path, environ_overrides={"REMOTE_ADDR": addr}).get_data(as_text=True)


def test_footer_only_in_phone_mode_and_only_for_local_requests(web, monkeypatch):
    monkeypatch.setenv("JOB_RAG_HOST", "0.0.0.0")
    assert "http://192.168.0.50:5000" in get(web, "127.0.0.1")
    assert "<br>" in get(web, "127.0.0.1") and "&lt;br" not in get(web, "127.0.0.1")  # 多個位址換行，不能被跳脫
    assert "192.168.0.50" not in get(web, "192.168.0.77")  # 手機自己不需要，也不洩漏網卡清單
    monkeypatch.delenv("JOB_RAG_HOST")
    assert "192.168.0.50" not in get(web, "127.0.0.1")  # 非手機模式不顯示


def test_footer_with_no_address_says_so_and_page_still_works(web, monkeypatch):
    import app as appmod
    monkeypatch.setenv("JOB_RAG_HOST", "0.0.0.0")
    monkeypatch.setattr(appmod.netinfo, "detect", lambda: [])
    html = get(web, "127.0.0.1")
    assert "求職情報問答" in html and "找不到" in html


def test_start_bat_phone_mode_is_opt_in():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    assert bat.count("JOB_RAG_HOST=0.0.0.0") == 1
    before = bat.split("JOB_RAG_HOST=0.0.0.0")[0]
    assert "phone" in before.splitlines()[-1].lower()  # 設定那一行必須在 phone 條件之內


def test_laptop_offline_keeps_original_results_and_shows_clear_error(web, monkeypatch):
    # 筆電斷網：真的 _post 走到 urlopen 時丟 URLError（DNS 解析失敗）。原文結果仍在，整理成答案顯示明確錯誤，不回示範答案。
    import socket
    import urllib.error
    import urllib.request

    def down(*a, **k):
        raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", down)
    c = web.test_client()
    html = c.get("/?q=鯨魚追蹤軟體").get_data(as_text=True)
    assert "鯨魚" in html and "整理成答案" in html  # 原文結果與按鈕都在
    html = c.get("/?q=鯨魚追蹤軟體&answer=1").get_data(as_text=True)
    assert "鯨魚" in html and "整理失敗" in html and "無法連到 DeepSeek" in html and "原文結果不受影響" in html
    assert "class='ans'" not in html

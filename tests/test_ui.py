"""簡約前端（票 15）：三種畫面共用同一份樣式；主題、無外部資源、顏色走變數、流程圖手機不換行。"""
import re

import pytest

from job_rag import about
from tests.test_about_data import root  # noqa: F401  (root 是 fixture)
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


@pytest.fixture
def pages(monkeypatch, root):  # noqa: F811
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    monkeypatch.setattr(about, "ROOT", root)
    import app as appmod
    c = appmod.app.test_client()
    ok = {"問答頁": c.get("/?q=鯨魚追蹤軟體").get_data(as_text=True), "說明頁": c.get("/about").get_data(as_text=True)}
    appmod._warm["state"] = "loading"
    try:
        ok["準備中"] = c.get("/").get_data(as_text=True)
    finally:
        appmod._warm["state"] = "ready"
    appmod._warm.update(state="error", error="壞了<b>")
    try:
        ok["啟動失敗"] = c.get("/").get_data(as_text=True)
    finally:
        appmod._warm.update(state="ready", error="")
    return ok


def test_every_screen_has_both_themes_viewport_and_reduced_motion(pages):
    for name, html in pages.items():
        assert "color-scheme:light dark" in html and "prefers-color-scheme:dark" in html, name
        assert "width=device-width" in html and "prefers-reduced-motion" in html, name


def test_no_external_resources_or_scripts(pages):
    for name, html in pages.items():
        assert not re.search(r"(src|href)=[\"']?(https?:)?//", html), name
        assert "<script" not in html and "@import" not in html and "<img" not in html, name


def test_colors_outside_root_tokens_are_variables(pages):
    # 除了 :root 的色票，不再出現寫死的色碼（含舊的 style='color:#c00'）
    for name, html in pages.items():
        rest = re.sub(r"<meta name=theme-color[^>]*>", "", re.sub(r":root\{[^}]*\}", "", html))  # theme-color 必須是色碼，由 test_pwa 核對
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b(?![^<]*</title>)", re.sub(r"href=\S+", "", rest)), name


def test_failure_screen_is_escaped_and_marked_as_error(pages):
    html = pages["啟動失敗"]
    assert "壞了&lt;b&gt;" in html and "class=err" in html.replace("'", "")


def test_status_screen_still_refreshes(pages):
    assert "http-equiv=refresh" in pages["準備中"] and "準備中" in pages["準備中"]


def test_flow_never_wraps_so_no_stray_arrow(pages):
    css = pages["說明頁"]
    assert "flex-wrap" not in re.search(r"\.flow\{[^}]*\}", css).group(0)  # 窄螢幕單欄、寬螢幕單列，不依賴換行

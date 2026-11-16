"""票 16：輕量 PWA。只有 manifest、圖示與 meta 標籤；不註冊 service worker。"""
import io
import json
import re

import pytest
from PIL import Image

from job_rag.ui import CSS
from tests.test_about_data import root  # noqa: F401
from tests.test_ui import pages  # noqa: F401  (fixture)
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    import app as appmod
    return appmod.app.test_client()


def test_every_screen_links_manifest_and_ios_tags(pages):  # noqa: F811
    for name, html in pages.items():
        h = html.replace("'", "").replace('"', "")
        assert "<link rel=manifest href=/manifest.webmanifest>" in h, name
        assert "apple-mobile-web-app-capable content=yes" in h, name
        assert "apple-mobile-web-app-status-bar-style" in h, name
        assert "<link rel=apple-touch-icon href=/static/icon-180.png>" in h, name
        assert re.search(r"theme-color content=#\w+ media=\(prefers-color-scheme: ?light\)", h), name
        assert re.search(r"theme-color content=#\w+ media=\(prefers-color-scheme: ?dark\)", h), name


def test_no_service_worker_anywhere(pages, client):  # noqa: F811
    for name, html in pages.items():
        assert "serviceWorker" not in html and "<script" not in html, name
    assert client.get("/sw.js").status_code == 404


def test_manifest_is_valid_json_with_required_fields(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.mimetype == "application/manifest+json"
    m = json.loads(r.get_data(as_text=True))
    assert m["name"] and m["short_name"] and len(m["short_name"]) <= 12
    assert m["start_url"] == "/" and m["display"] == "standalone"
    assert not m["start_url"].startswith("http") and "localhost" not in r.get_data(as_text=True)
    # 主題色與簡約風格的淺色底色一致（取自 ui.CSS 的 --bg）
    assert m["theme_color"] == m["background_color"] == re.search(r"--bg:(#\w+)", CSS).group(1)


def test_manifest_icons_exist_with_declared_size_and_type(client):
    icons = json.loads(client.get("/manifest.webmanifest").get_data(as_text=True))["icons"]
    assert {i["sizes"] for i in icons} >= {"192x192", "512x512"}
    for i in icons:
        r = client.get(i["src"])
        assert r.status_code == 200 and r.mimetype == i["type"] == "image/png", i
        assert "x".join(map(str, Image.open(io.BytesIO(r.data)).size)) == i["sizes"], i
    r = client.get("/static/icon-180.png")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.data)).size == (180, 180)


def test_manifest_served_while_warming_up(client):
    import app as appmod
    appmod._warm["state"] = "loading"
    try:
        assert client.get("/manifest.webmanifest").status_code == 200
    finally:
        appmod._warm["state"] = "ready"


def test_theme_color_metas_match_css_backgrounds(pages):  # noqa: F811
    light, dark = re.findall(r"--bg:(#\w+)", CSS)
    h = pages["問答頁"].replace("'", "")
    assert f"theme-color content={light} media=(prefers-color-scheme: light)" in h
    assert f"theme-color content={dark} media=(prefers-color-scheme: dark)" in h

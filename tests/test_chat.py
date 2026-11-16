"""票 21：公司對話頁（/c/<公司>）、/api/search、預設題目、「我能回答什麼」提示。DeepSeek 一律用替身。"""
import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

from job_rag import guard, retrieval
from job_rag.chat_ui import CHAT_JS
from job_rag.topics import topics
from tests.test_answer import FakePost, MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

ROOT = Path(__file__).parent.parent
Q = "鯨魚追蹤軟體"


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    monkeypatch.delenv("JOB_RAG_ACCESS_CODE", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    return appmod


def unescape(js):
    return re.sub(r"\\u([0-9a-f]{4})", lambda m: chr(int(m.group(1), 16)), js)


def attr(html, name):
    import html as h
    return json.loads(h.unescape(re.search(rf'data-{name}="([^"]*)"', html).group(1)))


# ---- 預設題目檔 ----
PRESETS = json.loads((ROOT / "job_rag" / "company_presets.json").read_text(encoding="utf-8"))


def test_every_live_company_has_3_to_5_presets_that_stand_alone():
    import app as appmod
    for label, _ in appmod.LIVE_COMPANIES:
        c = PRESETS["companies"][label]
        assert 3 <= len(c["presets"]) <= 5, label
        assert len({p["key"] for p in c["presets"]}) == len(c["presets"]), label
        for p in c["presets"]:
            assert label in p["q"] and p["q"].endswith("？") and p["label"], (label, p)  # 帶公司名，可獨立成句
        assert isinstance(c["thin"], bool)


def test_all_companies_presets_are_cross_company_and_name_no_company():
    import app as appmod
    assert 3 <= len(PRESETS["all"]) <= 5
    for p in PRESETS["all"]:
        assert not any(label in p["q"] for label, _ in appmod.LIVE_COMPANIES), p  # 否則會被自動偵測成單一公司


# ---- 提示用的主題統計：由語料算出 ----
def corpus(tmp_path, files):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_topics_follow_the_corpus_and_missing_never_lists_what_exists(tmp_path):
    c = corpus(tmp_path, {"01_丙公司.md": "# 01 丙\n\n## 1. 基本資料\n丙公司做雲端。\n\n## 4. 職缺\n職缺甲。\n\n### 4.1 後端\n職缺乙。\n\n## 5. 技術堆疊\nPython。\n",
                          "04_丁.md": "# 02 丁\n\n## 1. 基本資料\n丁公司做硬體。\n\n## 8. 近一年新聞\n新聞一則。\n"})
    t = topics("丙公司", corpus=c)
    assert t["have"] == ["公司簡介", "職缺資料（2 段）", "技術堆疊"] and t["segments"] == 4
    assert "近期新聞" not in t["have"]
    d = topics("丁", corpus=c)  # 換語料內容，主題與筆數就跟著變
    assert d["have"] == ["公司簡介", "近期新聞"] and not any("職缺" in x for x in d["have"])
    assert not set(t["missing"]) & {h.split("（")[0] for h in t["have"]}


@pytest.mark.parametrize("text,has", [
    ("薪資：月薪 40,000~42,000", True), ("年薪 81–108 萬", True),
    ("待遇面議（經常性薪資達 4 萬）", False),  # 面議沒有數字
    ("月薪四萬到六萬", False),  # 已知限制：只認阿拉伯數字
    ("薪資 | 依經驗", False),
])
def test_salary_rule_positive_and_negative(tmp_path, text, has):
    c = corpus(tmp_path, {"01_甲.md": f"# 01 戊\n\n## 4. 職缺\n{text}\n"})
    assert ("薪資範圍" not in topics("甲", corpus=c)["missing"]) is has


@pytest.mark.parametrize("text,has", [
    ("員工人數：25 人", True), ("員工 72 人", True), ("規模區間 1,001～5,000 人", True),
    ("應徵人數：6~10 人", False),  # 徵才人數不是員工人數
    ("人數：6~10 人", False), ("我們有很多員工", False),
])
def test_headcount_rule_positive_and_negative(tmp_path, text, has):
    c = corpus(tmp_path, {"02_乙.md": f"# 01 己\n\n## 1. 基本資料\n{text}\n"})
    assert ("員工人數" not in topics("乙", corpus=c)["missing"]) is has


def test_interview_and_reviews_are_always_missing(tmp_path):
    from job_rag.retrieval import NOT_COLLECTED
    c = corpus(tmp_path, {"03_丙.md": "# 01 庚\n\n## 1. 基本資料\n員工人數：25 人，月薪 50,000。\n"})
    assert topics("丙", corpus=c)["missing"] == [NOT_COLLECTED]


def test_all_company_topics_count_every_public_segment(tmp_path):
    c = corpus(tmp_path, {"01_丙公司.md": "# 01 丙\n\n## 1. 基本資料\n甲。\n", "04_丁.md": "# 02 丁\n\n## 1. 基本資料\n乙。\n"})
    assert topics(None, corpus=c)["segments"] == 2


# ---- 對話頁 ----
def page(web, label="藍新資訊"):
    r = web.app.test_client().get("/c/" + quote(label))
    return r.status_code, r.get_data(as_text=True)


def test_company_chat_page_structure(web):
    code, html = page(web)
    assert code == 200 and "<body class=chat" in html
    assert 'href="/">← 公司清單<' in html and "<b class=app>藍新資訊</b>" in html and 'href="/about">專案說明<' in html
    assert re.search(r'<button id=help type=button aria-label="可以問什麼">？</button>', html)  # 右上角「？」
    assert re.search(r'<form id=bar [^>]*><input id=qi name=q placeholder="例如：藍新資訊', html)  # 固定一個範例，沒有動畫
    assert html.count("<script>") == 1 and not re.search(r"<script[^>]*\bsrc\b", html)
    presets = attr(html, "presets")
    assert 3 <= len(presets) <= 5 and all("藍新資訊" in q for _, _, q in presets)
    assert "我可以回答關於藍新資訊的問題。你可以點下面的題目，或直接問。" in html.replace("&#39;", "'") or "我可以回答關於藍新資訊的問題" in html
    assert "<noscript>" in html and "name=faq" in html.split("<noscript>")[1]  # 沒有 JS 的退路


def test_all_companies_chat_page_and_unknown_company(web):
    code, html = page(web, "全部公司")
    assert code == 200 and 'data-scope=""' in html and 3 <= len(attr(html, "presets")) <= 5
    assert page(web, "不存在公司")[0] == 404


def test_hint_text_comes_from_the_corpus_and_is_honest_about_thin_companies(web):
    code, html = page(web, "藍新資訊")  # MINI 語料沒有藍新資訊：沒有任何主題，而且標示公開資料較少
    lines = attr(html, "hint")
    assert lines[0].startswith("這家公開資料較少（只有 0 段）")
    assert lines[1] == "這家有的資料：" and lines[2].startswith("這家沒有的資料：薪資範圍、員工人數")
    assert lines[3].startswith("你可以這樣問：「藍新資訊") and lines[3].count("「") == 2


def test_hint_lists_real_topics_for_a_company_in_the_corpus(web):
    lines = web._hint("甲科技", [("a", "x", "甲科技的問題一？"), ("b", "y", "甲科技的問題二？")], False)
    have = lines[0]
    assert have.startswith("這家有的資料：") and "公司簡介" in have and "技術堆疊" in have and "職缺資料（" in have
    assert "近期新聞" not in have  # 語料裡沒有
    assert lines[1].startswith("這家沒有的資料：") and "面試與評價" in lines[1]
    assert lines[2] == "你可以這樣問：「甲科技的問題一？」「甲科技的問題二？」"
    assert not any("較少" in x for x in lines)  # 沒標 thin，不亂說


def test_thin_note_needs_both_the_flag_and_few_segments(web):
    qs = [("a", "x", "甲科技的問題？")]
    assert web._hint("甲科技", qs, True)[0].startswith("這家公開資料較少")  # MINI 的甲科技只有幾段
    assert not any("較少" in x for x in web._hint("甲科技", qs, False))


def test_all_companies_hint_counts_companies_and_segments(web):
    lines = web._hint("", [("a", "x", "q？")], False)
    assert re.fullmatch(r"這裡同時搜 \d+ 家公司、共 \d+ 段公開資料。", lines[0]) and lines[1].startswith("沒有的資料：")


def test_script_shows_hint_on_open_and_on_help_button_and_keeps_chat_per_company(web):
    js = unescape(CHAT_JS)
    assert "getElementById('help')" in js and "function hint()" in js
    assert "function greet(){say(B.dataset.hello);hint()}" in js
    assert "'jr_chat:'+B.dataset.key" in js  # 每家公司各存一份
    assert "try{sessionStorage.setItem" in js and "try{old=JSON.parse(sessionStorage.getItem" in js  # 存取失敗不影響使用
    assert "eval(" not in js


def test_script_step_lines_map_to_real_requests(web):
    js = unescape(CHAT_JS)
    order = [js.index(x) for x in ("step('搜尋資料（範圍：", "api('/api/search'", "'找到 '", "step('整理答案')", "api('/api/answer'")]
    assert order == sorted(order)  # 每一行步驟都出現在對應的請求之前或之後，沒有預先顯示
    assert "我找不到很接近的內容，不確定有沒有答案" in js and "逾時或無法連線" in js


# ---- /api/search ----
def test_api_search_returns_hits_without_calling_deepseek(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    d = web.app.test_client().get("/api/search", query_string={"q": Q}).get_json()
    assert d["status"] == "ok" and d["hits"] and {"company", "file", "heading_path", "text"} <= set(d["hits"][0])
    assert post.calls == [] and len(web._limiter.stamps) == 0  # 搜尋不計用量


def test_api_search_company_filter_and_detection(web):
    c = web.app.test_client()
    d = c.get("/api/search", query_string={"q": Q, "company": "乙資訊"}).get_json()
    assert {h["company"] for h in d["hits"]} == {"乙資訊"} and d["detected"] is False
    d = c.get("/api/search", query_string={"q": "乙資訊 " + Q}).get_json()
    assert d["detected"] is True and d["company"] == "乙資訊"


def test_api_search_low_score_says_low_and_still_returns_text(web, monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    d = web.app.test_client().get("/api/search", query_string={"q": Q}).get_json()
    assert d["status"] == "low" and d["hits"]


def test_api_search_empty_question_and_never_leaks_private_text(web):
    c = web.app.test_client()
    assert c.get("/api/search").status_code == 400
    body = c.get("/api/search", query_string={"q": "離職率 珊瑚礁 企鵝密語 刺蝟密語"}).get_data(as_text=True)
    assert not any(w in body.replace("離職率 珊瑚礁 企鵝密語 刺蝟密語", "") for w in ("離職率", "珊瑚礁", "企鵝密語", "刺蝟密語"))


@pytest.mark.parametrize("path", ["/api/search?q=x", "/api/answer?q=x", "/answer?q=x"])
def test_json_endpoints_return_json_403_without_code(web, monkeypatch, path):
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", "abc-123")
    r = web.app.test_client().get(path)
    assert r.status_code == 403 and r.get_json()["status"] == "error" and "存取碼" in r.get_json()["message"]
    assert r.mimetype == "application/json"


def test_api_answer_alias_has_the_same_limits(web, monkeypatch):
    post = FakePost()
    monkeypatch.setattr(web, "_post", post)
    monkeypatch.setenv("JOB_RAG_ANSWER_LIMIT", "1")
    c = web.app.test_client()
    assert c.get("/api/answer", query_string={"q": Q}).get_json()["status"] == "ok"
    r = c.get("/api/answer", query_string={"q": Q})
    assert r.status_code == 429 and r.get_json()["status"] == "limit" and len(post.calls) == 1


def test_chat_pages_are_behind_the_access_code(web, monkeypatch):
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", "abc-123")
    c = web.app.test_client()
    assert c.get("/c/" + quote("藍新資訊")).status_code == 403 and c.get("/").status_code == 403
    assert c.get("/c/" + quote("藍新資訊"), query_string={"k": "abc-123"}).status_code == 200

"""票 14：公司名自動過濾、結果去重、預熱。語料用 tmp_path 現做的小語料，嵌入器用假的。"""
import pytest

from job_rag import retrieval, search
from job_rag.answer import answer
from job_rag.evaluate import evaluate, hit_rank
from job_rag.retrieval import detect_company
from tests.test_answer import FakePost
from tests.test_vector import fake_env  # noqa: F401  (autouse)

DUP = "神通資訊做雲端服務，獨特詞彙：海星。\n"


@pytest.fixture
def corpus(tmp_path):
    files = {
        "01_台灣大哥大.md": "# 台灣大哥大\n## 基本資料\n台灣大哥大做行動通訊，獨特詞彙：海馬。\n",
        "02_藍新資訊.md": "# 藍新資訊\n## 基本資料\n藍新資訊做金流相關系統。藍新金流是子公司，獨特詞彙：海龜。\n",
        "03_神通資訊.md": "# 神通資訊\n## 基本資料\n" + DUP,
        "04_聯合報.md": "# 聯合報\n## 基本資料\n聯合報做新聞，獨特詞彙：海鷗。\n## 職缺\n" + DUP,
        "補2_神通.md": "# 補2\n## 基本資料\n" + DUP.replace("，", "，  ") + "\n## 職缺\n神通資訊徵工程師 Python 3 年。\n",
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


# ---- 公司名偵測 ----
@pytest.mark.parametrize("question,want", [
    ("台灣大哥大有哪些業務？", "台灣大哥大"),
    ("台哥大有哪些業務？", "台灣大哥大"),          # 別名表
    ("聯合報系的職缺？", "聯合報"),                  # 別名「聯合報系」，同時含「聯合報」仍是同一家
    ("神通和神通資訊差在哪？", "神通資訊"),          # 別名＋全名，同一家
    ("台灣有哪些業務？", None),                      # 「台灣」不是「台灣大哥大」
    ("台灣大哥大和藍新資訊哪家薪水高？", None),      # 兩家：不過濾
    ("藍新金流是做什麼的？", None),                  # 近似詞，不在公司清單
    ("哪家公司有 Python 職缺？", None),
    ("", None),
])
def test_detect_company(corpus, question, want):
    assert detect_company(question, corpus=corpus) == want


def test_detect_unknown_alias_target_is_ignored(corpus):
    # 別名「華電」指向語料中沒有的公司：不能回傳一個查不到的公司
    assert detect_company("華電有哪些職缺？", corpus=corpus) is None


def test_detect_uses_whole_names_not_substrings(corpus):
    assert detect_company("藍新有哪些職缺？", corpus=corpus) is None
    assert detect_company("大哥大有哪些職缺？", corpus=corpus) is None


def test_search_detects_company_when_switched_on(corpus):
    r = search("台灣大哥大 海 獨特詞彙", corpus=corpus, method="bm25", k=10, detect=True)
    assert r and {x["company"] for x in r} == {"台灣大哥大"}
    r = search("台灣大哥大 海 獨特詞彙", corpus=corpus, method="bm25", k=10)
    assert len({x["company"] for x in r}) > 1  # 開關預設關：行為同以前


def test_explicit_company_wins_over_detection(corpus):
    r = search("台灣大哥大 海 獨特詞彙", corpus=corpus, method="bm25", k=10, company="聯合報", detect=True)
    assert r and {x["company"] for x in r} == {"聯合報"}


# ---- 去重 ----
def test_dedupe_merges_same_company_same_text_and_records_other_places(corpus):
    plain = search("海星", corpus=corpus, method="bm25", k=10)
    ded = search("海星", corpus=corpus, method="bm25", k=10, dedupe=True)
    assert [x["company"] for x in plain].count("神通資訊") == 2
    mine = [x for x in ded if x["company"] == "神通資訊"]
    assert len(mine) == 1
    kept = next(x for x in plain if x["company"] == "神通資訊")  # 沒去重時排最前的那份被保留
    assert (mine[0]["file"], mine[0]["heading_path"]) == (kept["file"], kept["heading_path"])
    gone = next(x for x in plain if x["company"] == "神通資訊" and x["file"] != kept["file"])
    assert mine[0]["also_in"] == [{"file": gone["file"], "heading_path": gone["heading_path"]}]


def test_dedupe_never_merges_across_companies(corpus):
    ded = search("海星", corpus=corpus, method="bm25", k=10, dedupe=True)
    assert {"神通資訊", "聯合報"} <= {x["company"] for x in ded}


def test_dedupe_off_has_no_also_in(corpus):
    assert all("also_in" not in x for x in search("海星", corpus=corpus, method="bm25", k=10))


def test_dedupe_does_not_merge_texts_that_differ(corpus):
    ded = search("神通資訊 Python 工程師", corpus=corpus, method="bm25", k=10, dedupe=True, company="神通資訊")
    assert any("Python 3 年" in x["text"] for x in ded)  # 職缺段落與基本資料段落不同，不被併掉
    assert all(x["also_in"] == [] for x in ded if "Python" in x["text"])


def test_dedupe_fills_k_after_merging(corpus):
    ded = search("神通資訊", corpus=corpus, method="bm25", k=2, dedupe=True, company="神通資訊")
    assert len(ded) == 2  # 合併後仍補滿 k，不是先切 k 再合併


# ---- 評分的命中判斷 ----
G = [{"file": "補2_神通.md", "heading": "基本資料"}]


def test_hit_rank_counts_also_in_places():
    res = [{"file": "03_神通資訊.md", "heading_path": "基本資料",
            "also_in": [{"file": "補2_神通.md", "heading_path": "基本資料"}]}]
    assert hit_rank(res, G) == 1


def test_hit_rank_also_in_miss_when_not_gold():
    res = [{"file": "03_神通資訊.md", "heading_path": "基本資料",
            "also_in": [{"file": "補2_神通.md", "heading_path": "基本資料風險"}]}]
    assert hit_rank(res, G) is None


def test_evaluate_gold_in_merged_copy_still_hits(corpus):
    qs = [{"id": "q", "question": "海星", "answerable": True, "gold": G}]
    for dedupe in (False, True):
        rep = evaluate(qs, method="bm25", corpus=corpus, dedupe=dedupe)
        assert rep["scores"]["ranks"]["q"] is not None, dedupe


def test_evaluate_detect_switch(corpus):
    qs = [{"id": "q", "question": "聯合報的海鷗", "answerable": True,
           "gold": [{"file": "04_聯合報.md", "heading": "基本資料"}]}]
    assert evaluate(qs, method="bm25", corpus=corpus, detect=True)["scores"]["ranks"]["q"] == 1


# ---- 出處清單不重複 ----
def test_answer_sources_have_no_duplicates(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    h = {"company": "甲", "file": "a.md", "heading_path": "基本資料", "text": "第一段"}
    r = answer("問題", [h, h | {"text": "第二段"}], post=FakePost(), env_file="none")
    assert r["sources"] == [{"company": "甲", "file": "a.md", "heading_path": "基本資料"}]


# ---- 介面 ----
@pytest.fixture
def client(corpus, monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(corpus))
    monkeypatch.delenv("JOB_RAG_DETECT", raising=False)
    monkeypatch.delenv("JOB_RAG_DEDUPE", raising=False)
    import app as appmod
    return appmod, appmod.app.test_client()


def page(c, url, **kw):
    return c.get(url, **kw).get_data(as_text=True).split("</form>", 1)[1]


def test_ui_detects_company_and_says_so(client):
    _, c = client
    body = page(c, "/?q=台灣大哥大有哪些業務")
    assert "已偵測到公司：台灣大哥大" in body and "<b>聯合報</b>" not in body


def test_ui_selected_company_wins_and_no_detection_note(client):
    _, c = client
    body = page(c, "/?q=台灣大哥大有哪些業務&company=聯合報")
    assert "已偵測到公司" not in body and "<b>台灣大哥大</b>" not in body and "<b>聯合報</b>" in body


def test_ui_two_companies_no_filter_no_note(client):
    _, c = client
    body = page(c, "/?q=台灣大哥大和聯合報 業務")
    assert "已偵測到公司" not in body


def test_ui_switches_off_by_env(client, monkeypatch):
    _, c = client
    monkeypatch.setenv("JOB_RAG_DETECT", "0")
    assert "已偵測到公司" not in page(c, "/?q=台灣大哥大有哪些業務")


def test_ui_shows_also_in_and_off_switch(client, monkeypatch):
    _, c = client
    body = page(c, "/?q=神通資訊 海星&company=神通資訊")
    assert body.count("海星。") == 1 and "也出現於" in body and "03_神通資訊.md" in body
    monkeypatch.setenv("JOB_RAG_DEDUPE", "0")
    body = page(c, "/?q=神通資訊 海星&company=神通資訊")
    assert body.count("海星。") == 2 and "也出現於" not in body


# ---- 預熱 ----
def test_while_warming_page_says_preparing_and_does_not_search(client, monkeypatch):
    appmod, c = client
    monkeypatch.setattr(appmod, "search", lambda *a, **k: pytest.fail("預熱期間不該查詢"))
    appmod._warm["state"] = "loading"
    try:
        r = c.get("/?q=台灣大哥大有哪些業務")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "準備中" in html and "class='hit" not in html and "可能沒有答案" not in html
        assert "refresh" in html  # 自動重新整理
    finally:
        appmod._warm["state"] = "ready"


def test_warmup_runs_search_once_then_page_is_ready(client, monkeypatch):
    appmod, c = client
    calls = []
    real = appmod.search
    monkeypatch.setattr(appmod, "search", lambda *a, **k: calls.append(1) or real(*a, **k))
    appmod._warm["state"] = "loading"
    appmod.warmup()
    assert appmod._warm["state"] == "ready" and calls
    assert "準備中" not in c.get("/").get_data(as_text=True)


def test_warmup_failure_is_shown_not_hidden(client, monkeypatch):
    appmod, c = client
    monkeypatch.setattr(appmod, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("找不到模型：x")))
    appmod.warmup()
    try:
        html = c.get("/?q=abc").get_data(as_text=True)
        assert "啟動失敗" in html and "找不到模型" in html and "class='hit" not in html
    finally:
        appmod._warm["state"] = "ready"

"""票 31：跨公司提問。偵測規則（含反例）、每家取段、展示模式不含私人段落、API 欄位、提示規則只在跨公司模式。假嵌入器、假 DeepSeek。"""
import json

import pytest

from job_rag import cross_search, guard, is_cross, retrieval
from job_rag.answer import CROSS_RULES, SYSTEM, answer
from tests.test_answer import FakePost, MINI  # noqa: F401
from tests.test_about_data import root  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

YES = ["哪一間薪水比較好？", "哪些公司用 Python？", "哪家公司有後端職缺", "哪間公司值得優先投", "各家的技術堆疊有什麼不同",
       "所有公司的薪資範圍", "推薦哪幾家投遞", "薪水比較高的是誰", "哪個公司有 AI 職缺",
       "Python 後端工程師的職缺有哪些？", "哪些職缺要會 Python？", "有哪些 Python 後端職缺"]
NO = ["甲科技比較重視什麼", "哪裡可以報名", "最近有什麼新聞", "甲科技和乙資訊哪間比較好",  # 提到公司（一家或兩家）都不算
      "各種職缺有哪些", "這份職缺有哪些要求", "職缺要會 Python 嗎", "報名要準備哪些文件", "薪資範圍是多少", "有推薦信嗎", "公司最近在做什麼"]


@pytest.mark.parametrize("q", YES)
def test_cross_questions_detected(q):
    assert retrieval.asks_all(q, MINI) and is_cross(q, MINI)


@pytest.mark.parametrize("q", NO)
def test_non_cross_questions_not_detected(q):
    assert not retrieval.asks_all(q, MINI)  # 詞表只決定追問時要不要接上一題


@pytest.mark.parametrize("q", NO)
def test_routing_ignores_wording_and_only_checks_company_names(q):
    """分流不看問法：沒提到公司就是跨公司；提到公司（一家或兩家）就不是。"""
    assert is_cross(q, MINI) == ("甲科技" not in q and "乙資訊" not in q)


def test_cross_search_one_per_company_sorted_and_public_only():
    hits = cross_search("哪間公司有後端職缺", per=1, corpus=MINI)
    assert sorted(h["company"] for h in hits) == ["乙資訊", "甲科技"]
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    assert len({(h["company"], h["file"], h["heading_path"], h["text"]) for h in hits}) == len(hits)
    blob = json.dumps(hits, ensure_ascii=False)
    for secret in ("刺蝟密語", "企鵝密語", "河馬密語", "海豹密語", "狐獴密語"):  # 私人（排除）段落的獨特詞
        assert secret not in blob
    assert all("private" not in h for h in hits)
    assert len(cross_search("哪間公司有後端職缺", per=2, corpus=MINI)) > len(hits)  # 每家段數可調


def test_demo_cross_search_never_reaches_selfdata(monkeypatch, tmp_path):
    sd = tmp_path / "selfdata"
    sd.mkdir()
    (sd / "x.md").write_text("# 甲科技 面經\n獨特詞彙：自用面經密語", encoding="utf-8")
    monkeypatch.setenv("JOB_RAG_SELF_DIR", str(sd))
    assert "自用面經密語" not in json.dumps(cross_search("哪間公司", per=3, corpus=MINI), ensure_ascii=False)


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    for k in ("JOB_RAG_ACCESS_CODE", "JOB_RAG_ANSWER_LIMIT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("JOB_RAG_FAKE_ANSWER", "ok")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    import app as appmod
    monkeypatch.setattr(appmod, "_limiter", guard.RateLimit())
    monkeypatch.setattr(retrieval, "CROSS_FLOOR", 0.0)
    return appmod.app.test_client()


def test_api_search_cross_adds_fields_and_covers_companies(web):
    d = web.get("/api/search", query_string={"q": "哪間公司有後端職缺"}).get_json()
    assert d["status"] == "ok" and d["cross"] is True and d["per"] == retrieval.PER_COMPANY
    assert {h["company"] for h in d["hits"]} == {"甲科技", "乙資訊"}
    assert d["threshold"] == retrieval.CROSS_FLOOR and all("score" in h for h in d["hits"])
    assert {"company", "detected", "expanded", "search_ms"} <= set(d)  # 舊欄位仍在


def test_single_company_paths_unchanged(web):
    for q, comp in (("甲科技比較重視什麼", ""), ("哪間公司有後端職缺", "甲科技")):
        d = web.get("/api/search", query_string={"q": q, "company": comp}).get_json()
        assert d["cross"] is False and d["threshold"] == (retrieval.NOT_FOUND_THRESHOLD if d["company"] == "" else round(retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP, 3))
        assert len({h["company"] for h in d["hits"]}) == 1


def test_cross_low_uses_cross_floor_not_threshold(web, monkeypatch):
    monkeypatch.setattr(retrieval, "CROSS_FLOOR", 9.0)
    assert web.get("/api/search", query_string={"q": "哪間公司有後端職缺"}).get_json()["status"] == "low"
    assert web.get("/api/answer", query_string={"q": "哪間公司有後端職缺"}).get_json()["status"] == "low"


def test_api_answer_cross_ok(web):
    d = web.get("/api/answer", query_string={"q": "哪間公司有後端職缺"}).get_json()
    assert d["status"] == "ok" and d["answer"]


def test_cross_rules_only_in_cross_prompt(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    hit = {"company": "甲科技", "file": "f", "heading_path": "h", "text": "t"}
    a, b = FakePost(), FakePost()
    answer("哪間比較好", [hit], post=a, cross=True)
    answer("問題", [hit], post=b)
    sys_a, sys_b = a.calls[0][2]["messages"][0]["content"], b.calls[0][2]["messages"][0]["content"]
    assert sys_a == SYSTEM + CROSS_RULES and sys_b == SYSTEM
    for w in ("逐家公司", "資料沒寫", "不排名", "[n]"):
        assert w in CROSS_RULES


def test_cross_search_companies_filter_limits_to_listed_companies():
    hits = cross_search("哪間公司有後端職缺", per=3, corpus=MINI, companies={"甲科技"})
    assert hits and {h["company"] for h in hits} == {"甲科技"}


# ---- /about 的跨公司一行：數字取自輸出檔，過期或缺檔就不寫 ----
def _cross_out(root, digest=None):
    import hashlib
    from tests.test_about_data import put
    q = '{"questions": []}'
    put(root, "eval/questions_cross.json", q)
    d = digest or hashlib.sha1(q.encode("utf-8")).hexdigest()[:16]
    row = lambda i, a, st, n: {"id": i, "answerable": a, "status": st, "n_correct": n, "coverage": (0.5 if a else None)}
    put(root, "eval/results_cross.json", {"digest": d, "floor": 0.534, "per_default": 2,
        "per": {"2": [row("x1", True, "ok", 2), row("x2", True, "low", 0), row("u1", False, "low", 0)]}})


def test_about_cross_line_comes_from_output_file(root):
    from job_rag.about import load
    _cross_out(root)
    x = load(root)["cross_eval"]
    assert (x["n"], x["passed"], x["n_answerable"], x["answerable_ok"], x["floor"], x["per"]) == (3, 2, 2, 1, 0.534, 2)


def test_about_cross_line_omitted_when_missing_or_stale(root):
    from job_rag.about import load
    assert load(root)["cross_eval"] is None
    _cross_out(root, digest="0" * 16)
    assert load(root)["cross_eval"] is None


def test_cross_question_after_a_company_question_is_not_turned_into_single_company(web):
    hist = json.dumps([{"q": "甲科技是做什麼的？", "a": "做後端 [1]", "m": "demo"}], ensure_ascii=False)
    d = web.get("/api/search", query_string={"q": "哪間公司有後端職缺", "history": hist}).get_json()
    assert d["cross"] is True and d["company"] == ""


def test_hybrid_picks_do_not_change_the_gate_score_and_have_no_duplicates(monkeypatch):
    """挑段用混合名次；每段帶的 top 是 bge-m3 最高分（per=1 時等於舊做法取到的最高分），拒答只看它。"""
    import app
    q = "哪間公司有後端職缺"
    hits = cross_search(q, per=3, corpus=MINI)
    pool, ranked = retrieval._rank_vector(retrieval._root(MINI, "demo"), "bge-m3", q, None)
    best = max(sc for i, sc in ranked if pool[i]["company"] != retrieval.GENERAL)
    assert {h["top"] for h in hits} == {best}
    keys = [(h["file"], h["heading_path"], h["text"]) for h in hits]
    assert len(keys) == len(set(keys)) and [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    assert cross_search(q, per=0, corpus=MINI) == []
    one = {"company": "甲", "score": 0.1}
    monkeypatch.setattr(retrieval, "CROSS_FLOOR", 0.5)
    assert not app._low_cross([one | {"top": 0.6}])  # 取到的段分數低，但全體最高分過門檻：不拒答
    assert app._low_cross([one | {"top": 0.4}]) and app._low_cross([one]) and app._low_cross([])  # 負向：最高分不到就拒答；沒有 top 用段落分數

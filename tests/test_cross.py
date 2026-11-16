"""票 31：跨公司提問。偵測規則（含反例）、每家取段、展示模式不含私人段落、API 欄位、提示規則只在跨公司模式。假嵌入器、假 DeepSeek。"""
import json

import pytest

from job_rag import cross_search, guard, is_cross, retrieval
from job_rag.answer import CROSS_RULES, SYSTEM, answer
from tests.test_answer import FakePost, MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

YES = ["哪一間薪水比較好？", "哪些公司用 Python？", "哪家公司有後端職缺", "哪間公司值得優先投", "各家的技術堆疊有什麼不同",
       "所有公司的薪資範圍", "推薦哪幾家投遞", "薪水比較高的是誰", "哪個公司有 AI 職缺"]
NO = ["甲科技比較重視什麼", "哪裡可以報名", "最近有什麼新聞", "甲科技和乙資訊哪間比較好",  # 提到公司（一家或兩家）都不算
      "各種職缺有哪些", "報名要準備哪些文件", "薪資範圍是多少", "有推薦信嗎", "公司最近在做什麼"]


@pytest.mark.parametrize("q", YES)
def test_cross_questions_detected(q):
    assert is_cross(q, MINI)


@pytest.mark.parametrize("q", NO)
def test_non_cross_questions_not_detected(q):
    assert not is_cross(q, MINI)


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
        assert d["cross"] is False and d["threshold"] == retrieval.NOT_FOUND_THRESHOLD
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

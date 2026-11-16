"""/threshold：資料層用手算小例子；缺檔不報 500；常數改了頁面跟著變；/about 的端到端脈絡。"""
import re

from job_rag import retrieval, threshold_page as tp
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import BAD, client  # noqa: F401


def pt(id_, s, a, g="main", sc=False):
    return {"id": id_, "q": id_, "s": s, "a": a, "g": g, "sc": sc}


PTS = [pt("a1", 0.9, True), pt("a2", 0.8, True), pt("a3", 0.65, True, sc=True), pt("a4", 0.69, True),
       pt("u1", 0.5, False), pt("u2", 0.64, False, sc=True), pt("x1", 0.6, True, "cross"), pt("x2", 0.5, False, "cross")]


def test_counts_by_hand():
    # t=0.7、drop=0.08：a3、u2 用 0.62；跨公司用 floor=0.55
    c = tp.counts(PTS, 0.7, 0.08, 0.55)
    # 有答案：a1、a2 放行，a3(.65>=.62) 放行，a4(.69<.7) 被擋 → 3/4；沒答案：u1 擋住，u2(.64>=.62) 放行 → 1/2；錯 = a4 + u2
    assert c["main"] == {"a": 3, "b": 4, "c": 1, "d": 2, "n": 2}
    assert c["cross"] == {"a": 1, "b": 1, "c": 1, "d": 1, "n": 0}  # .6>=.55 放行；.5<.55 擋住
    assert tp.total(c) == {"a": 3, "b": 4, "c": 1, "d": 2, "n": 2}  # 跨公司不算進上方三個數字


def test_score_equal_to_threshold_passes_like_retrieval():
    c = tp.counts([pt("u", 0.7, False), pt("a", 0.7, True)], 0.7, 0.08, 0.5)
    assert c["main"]["c"] == 0 and c["main"]["a"] == 1  # 「低於」才擋：等於門檻放行


def test_gray_zone_and_no_overlap():
    assert tp.gray_zone(PTS) is None  # 有答案最低 .65 > 沒答案最高 .64：沒有重疊（跨公司不算）
    assert tp.gray_zone([pt("a", 0.6, True), pt("u", 0.7, False)]) == (0.6, 0.7)


def test_lanes_separate_equal_scores():
    lanes, n = tp._lanes([pt("a", 0.7, True), pt("b", 0.7, True), pt("c", 0.9, True)], 0.4, 0.9)
    assert n == 2 and sorted(k for p, _, k in lanes if p["s"] == 0.7) == [0, 1]


def test_load_missing_sources_marks_them_and_never_raises(root):  # noqa: F811
    d = tp.load(root)
    assert {p["id"] for p in d["pts"]} == {"a1", "a2", "a3", "a4", "u1"}
    assert set(d["miss"]) == {"真實問法", "跨公司題"} and d["e2e"] is None
    h = tp.render(d)
    assert "缺資料" in h and "端到端拒答：缺資料" in h


def test_stale_methods_file_is_missing_not_used(root):  # noqa: F811
    put(root, "eval/questions.json", {"questions": [{"id": "z", "question": "新題？", "answerable": True, "gold": []}]})
    d = tp.load(root)
    assert d["pts"] == [] and "評估題組" in d["miss"]


def test_route_ok_without_files_and_constants_come_from_code(client, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(tp, "ROOT", tmp_path)  # 完全沒有輸出檔
    r = client[1].get("/threshold")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert f"data-t={retrieval.NOT_FOUND_THRESHOLD!r}" in h and "缺資料" in h
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.75)
    monkeypatch.setattr(retrieval, "SCOPED_DROP", 0.1)
    h = client[1].get("/threshold").get_data(as_text=True)
    assert "data-t=0.75 data-drop=0.1 " in h and "<output id=tv>0.750</output>" in h and "<output id=ts>0.650</output>" in h


def test_page_counts_match_data_and_is_clean(client, root, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tp, "ROOT", root)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.7)
    h = client[1].get("/threshold").get_data(as_text=True)
    # fixture：有答案 .9 .8 .65 .69、沒答案 .5；門檻 .7 → 2/4、1/1、錯 2
    assert re.search(r"<b id=ca>2/4</b>.*<b id=cu>1/1</b>.*<b id=cw>2</b>", h, re.S)
    assert "<script src" not in h and "<link rel=stylesheet" not in h and "https://" not in h
    assert not any(w in h for w in BAD) and "不是最佳解" in h


def test_threshold_page_needs_access_code(monkeypatch, client):  # noqa: F811
    monkeypatch.setenv("JOB_RAG_ACCESS_CODE", "sesame123")
    assert client[1].get("/threshold").status_code == 403
    assert client[1].get("/threshold", query_string={"k": "sesame123"}).status_code == 200


E2E = {"n": 2, "refused": 2, "by_gate": 1, "by_answer_layer": 1, "rows": [{"refused": True}, {"refused": True}]}


def test_about_adds_end_to_end_context_next_to_blocked_counts(client, root):  # noqa: F811
    put(root, "eval/results_endtoend.json", E2E)
    h = client[1].get("/about?all=1").get_data(as_text=True)
    assert h.count("（再加答案層，端到端 2/2 拒答）") >= 3 and "href=/threshold" in h
    for m in re.finditer(r"擋住 \d+/\d+", h):  # 每一個「擋住 a/b」後面都帶著這個脈絡
        assert h[m.end(): m.end() + 6] == "（再加答案層"


def test_about_omits_it_when_file_missing_or_inconsistent(client, root):  # noqa: F811
    assert "端到端" not in client[1].get("/about?all=1").get_data(as_text=True)
    put(root, "eval/results_endtoend.json", E2E | {"refused": 1})  # 與逐題對不上：不採用
    assert "端到端" not in client[1].get("/about?all=1").get_data(as_text=True)


# ---- 票 38：題目卡（問了什麼、答了什麼） ----
import json  # noqa: E402

ANS = {"deepseek_calls": 3, "rows": [
    {"id": "a1", "set": "questions", "question": "甲的資本額？", "company": None, "answerable": True, "top_score": 0.9, "threshold_used": 0.7, "search_status": "ok",
     "detected_company": "甲", "answer": "資本額是 1 億 </script><b>x</b>", "answer_status": "ok", "sources": [{"company": "甲", "title": "1. 基本資料"}], "date": "2026-11-16", "run": 1},
    {"id": "u1", "set": "questions", "question": "戊的董事長喜歡什麼？", "company": None, "answerable": False, "top_score": 0.5, "threshold_used": 0.7, "search_status": "low",
     "answer": None, "answer_status": "skipped_low", "sources": [], "date": "2026-11-16", "run": 1},
    {"id": "a2", "set": "questions", "question": "舊題目文字", "search_status": "ok", "answer": "不該出現", "answer_status": "ok", "sources": []},  # 題目對不上：不採用
]}


def cards_of(h):
    return json.loads(re.search(r"<script type=application/json id=pd>(.*?)</script>", h, re.S).group(1))


def test_cards_match_answers_file_and_stale_rows_are_dropped(root):  # noqa: F811
    put(root, "eval/results_answers.json", ANS)
    c = tp.load(root)["cards"]
    assert c["main:a1"]["run"]["answer"].startswith("資本額是") and c["main:a1"]["run"]["sources"][0]["title"] == "1. 基本資料"
    assert c["main:a1"]["gold"] == [{"company": "甲", "title": "1. 基本資料"}]  # 檔名只留公司名
    assert outcome_of(c["main:u1"]) == "擋住" and c["main:u1"]["gold"] == []
    assert c["main:a2"]["run"] is None  # 問題文字改了就不用舊答案
    assert c["main:a3"]["run"] is None  # 沒記錄：卡片會寫「這題沒有記錄答案」


def outcome_of(card):
    return tp.outcome(card["run"])


def test_page_embeds_cards_safely_and_lists_every_point(client, root, monkeypatch):  # noqa: F811
    put(root, "eval/results_answers.json", ANS)
    monkeypatch.setattr(tp, "ROOT", root)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.7)
    h = client[1].get("/threshold").get_data(as_text=True)
    assert cards_of(h)["main:a1"]["run"]["answer"] == "資本額是 1 億 </script><b>x</b>"  # </script> 不會提早結束資料區
    assert h.count("class=t-r ") == 5 and "<b>x</b>" not in h.replace("\u003c", "")
    assert not any(w in h for w in BAD)


def test_page_without_answers_file_still_renders_cards_as_missing(client, root, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tp, "ROOT", root)
    r = client[1].get("/threshold")
    assert r.status_code == 200
    c = cards_of(r.get_data(as_text=True))
    assert c and all(v["run"] is None for v in c.values())
    assert "這題沒有記錄答案" in r.get_data(as_text=True)  # 卡片腳本裡的缺資料說明


def test_same_id_in_two_question_sets_gets_two_cards(root):  # noqa: F811
    put(root, "eval/questions_cross.json", {"questions": [{"id": "a1", "question": "跨公司的 a1", "answerable": True, "keywords": ["x"]}]})
    import hashlib
    put(root, "eval/results_cross.json", {"digest": hashlib.sha1((root / "eval/questions_cross.json").read_bytes()).hexdigest()[:16],
                                          "per_default": 3, "per": {"3": [{"id": "a1", "top": 0.6, "answerable": True}]}})
    d = tp.load(root)
    assert {p["k"] for p in d["pts"] if p["id"] == "a1"} == {"main:a1", "cross:a1"}
    assert len(d["cards"]) == len(d["pts"])


def test_badge_blocked_pass_and_no_record():
    p = pt("a", 0.8, True)
    ran = {"run": {"search": "ok", "ans_status": "ok", "answer": "查無"}}
    assert tp.badge(p, ran, 0.7, 0.08, 0.5) == "查無" and tp.badge(p, {"run": None}, 0.7, 0.08, 0.5) == "放行"
    assert tp.badge(p, ran, 0.85, 0.08, 0.5) == "擋住"  # 拖高門檻後被擋，不管實跑結果
    assert tp.badge(p, {"run": {"search": "ok", "ans_status": "ok", "answer": "查無，因為…"}}, 0.7, 0.08, 0.5) == "回答"  # 只有整句剛好是「查無」才算查無
    assert tp.badge(p, {"run": {"search": "ok", "ans_status": "error", "answer": None}}, 0.7, 0.08, 0.5) == "失敗"

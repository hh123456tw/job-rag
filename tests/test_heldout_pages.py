"""票 39：/about 與 /threshold 的獨立測試題數字必須取自輸出檔；缺檔或過期就維持原句、不美化。"""
import json
import re

from job_rag import about, threshold_page as tp
from job_rag.evaluate import questions_digest
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import client  # noqa: F401

QS = [{"id": "h01", "question": "甲的資本額？", "answerable": True, "company": "甲", "gold": [{"file": "f", "heading": "h", "quote": "q"}]},
      {"id": "h02", "question": "乙有員工餐廳嗎？", "answerable": False, "gold": []},
      {"id": "h03", "question": "哪家公司有健身房？", "answerable": False, "gold": []},
      {"id": "h04", "question": "哪些公司用 Python？", "answerable": True, "gold": [], "keywords": ["Python"]}]
ANS = [("h01", "ok", "資本額 1 億"), ("h02", "ok", "查無"), ("h03", "skipped_low", None), ("h04", "ok", "甲、乙")]


def held_files(root, digest=None, answers=True):  # noqa: F811
    put(root, "eval/questions_heldout.json", {"questions": QS})
    put(root, "eval/results_heldout.json", {
        "digest": digest or questions_digest(QS), "n": 4, "n_answerable": 1, "n_unanswerable": 1,
        "metrics": {"hit@1": 0.5, "hit@3": 0.75, "hit@5": 0.8, "mrr": 0.625}, "ci": {"hit@3": [0.5, 0.9], "mrr": [0.4, 0.8], "hit@1": [0, 1], "hit@5": [0, 1]},
        "unanswerable_blocked_total": 1, "unanswerable_total": 2,
        "scores": {"h01": 0.8, "h02": 0.7}, "routes": {"h01": "公司頁內提問", "h02": "偵測到公司"},
        "cross": [{"id": "h03", "answerable": False, "top": 0.4, "status": "low", "pass": True}, {"id": "h04", "answerable": True, "top": 0.6, "status": "ok", "pass": False}]})
    if answers:
        put(root, "eval/results_heldout_answers.json", {"rows": [
            {"id": i, "question": next(q["question"] for q in QS if q["id"] == i), "answer_status": st, "answer": a} for i, st, a in ANS]})


def test_numbers_come_from_the_output_files(root):  # noqa: F811
    held_files(root)
    x = about._heldout(root)
    assert (x["hit3"], x["mrr"], x["blocked_u"], x["n_unanswerable"], x["e2e"]) == (0.75, 0.625, 1, 2, {"refused": 2, "n": 2})


def test_missing_or_stale_output_returns_none_and_answers_missing_drops_only_e2e(root):  # noqa: F811
    assert about._heldout(root) is None
    held_files(root, digest="old")
    assert about._heldout(root) is None                         # 題檔變了：不用舊數字
    held_files(root)
    (root / "eval/results_heldout_answers.json").write_text("{壞掉", encoding="utf-8")
    x = about._heldout(root)
    assert x and x["e2e"] is None
    put(root, "eval/results_heldout_answers.json", {"rows": [{"id": "h01", "question": "改過的題目"}]})
    assert about._heldout(root)["e2e"] is None                  # 答案和題目對不上：不採用


def test_about_replaces_the_no_independent_test_sentence_only_when_output_exists(client, root):  # noqa: F811
    h = client[1].get("/about?all=1").get_data(as_text=True)
    assert "沒有獨立測試題" in h and "沒用來調參" not in h
    held_files(root)
    h = client[1].get("/about?all=1").get_data(as_text=True)
    assert "沒有獨立測試題" not in h
    assert "另有 4 題獨立測試題（沒用來調參）：Hit@3 ＝ 0.750（95% 區間 0.500–0.900）" in h
    assert "MRR ＝ 0.625" in h and "沒答案題檢索擋住 1/2、端到端拒答 2/2" in h


def test_threshold_draws_squares_and_keeps_headline_numbers_unchanged(client, root, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tp, "ROOT", root)
    before = client[1].get("/threshold").get_data(as_text=True)
    held_files(root)
    h = client[1].get("/threshold").get_data(as_text=True)
    assert h.count("<rect class=d") == 4 and "<rect class=d" not in before
    nums = lambda t: re.search(r"<b id=ca>.*?</b>.*?<b id=cu>.*?</b>.*?<b id=cw>.*?</b>", t, re.S).group(0)
    assert nums(h) == nums(before)                               # 上方三個數字不含獨立測試題
    assert "方形：獨立測試題" in h and "獨立測試題（沒用來調參）的 2 道沒有答案的題" in h and "端到端拒答 2/2" in h
    cards = json.loads(re.search(r"<script type=application/json id=pd>(.*?)</script>", h, re.S).group(1))
    assert cards["held:h02"]["run"]["answer"] == "查無" and cards["held:h01"]["gold"]


def test_threshold_stale_held_output_is_reported_missing_not_drawn(client, root, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tp, "ROOT", root)
    held_files(root, digest="old")
    h = client[1].get("/threshold").get_data(as_text=True)
    assert "<rect class=d" not in h and "獨立測試題" in h and "過期" in h


def test_by_type_and_cross_are_reported_separately_not_only_the_pooled_average(client, root):  # noqa: F811
    held_files(root)
    p = root / "eval/results_heldout.json"
    r = json.loads(p.read_text(encoding="utf-8"))
    r["by_type"] = {"單一公司": {"n": 3, "hit@3": 1.0, "mrr": 0.9}, "職缺": {"n": 2, "hit@3": 0.5, "mrr": 0.4}}
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    x = about._heldout(root)
    assert x["cross_n"] == 1 and x["cross_pass"] == 0 and x["by_type"]["職缺"]["hit@3"] == 0.5
    h = client[1].get("/about?all=1").get_data(as_text=True)
    assert "分題型：單一公司 3 題 Hit@3 1.000、MRR 0.900；職缺 2 題 Hit@3 0.500、MRR 0.400；跨公司題 0/1 通過關鍵字檢查" in h


def test_held_slide_names_the_real_question_count_and_splits_job_list_from_single_company(client, root):  # noqa: F811
    held_files(root)
    p = root / "eval/results_heldout.json"
    r = json.loads(p.read_text(encoding="utf-8"))
    r["by_type"] = {"單一公司": {"n": 3, "hit@3": 1.0, "mrr": 0.9}, "職缺": {"n": 2, "hit@3": 0.5, "mrr": 0.4}}
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    h = client[1].get("/about").get_data(as_text=True)
    assert "30 題對 4 題" in h and "40 題" not in h
    assert "職缺：Hit@3 0.50（1/2）" in h and "單一公司：Hit@3 1.00（3/3）" in h  # 小數，括號補題數
    assert "標準答案沒人工確認" in h


def test_score_slide_has_one_bar_per_type_with_values(client, root):  # noqa: F811
    held_files(root)
    p = root / "eval/results_heldout.json"
    r = json.loads(p.read_text(encoding="utf-8"))
    r["by_type"] = {"單一公司": {"n": 3, "hit@3": 1.0, "mrr": 0.9}, "職缺": {"n": 2, "hit@3": 0.5, "mrr": 0.4}}
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    h = client[1].get("/about").get_data(as_text=True)
    assert "哪裡強、哪裡弱" in h
    assert 'class="bar gx ok"' in h and 'class="bar gx bad"' in h  # 1.0 綠、0.5 紅
    sec = h[h.index("哪裡強、哪裡弱"):]
    sec = sec[:sec.index("</section>")]
    assert ">1.00（3/3）<" in sec and ">0.50（1/2）<" in sec  # 標準指標寫小數，括號補題數
    assert ">1.00<" not in sec and ">3/3<" not in sec  # 不單獨出現其中一種
    assert "職缺題較弱的可能原因（我的推論）" in sec  # 職缺 0.5：下方寫原因
    r["by_type"]["職缺"]["hit@3"] = 1.0
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    assert "職缺題較弱的可能原因" not in client[1].get("/about").get_data(as_text=True)  # 不弱就不寫

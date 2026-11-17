"""票 33：/about 的數字和輸出檔一致；新 20 題輸出缺檔或過期就略過那一句；生成層標明量測時的設定。"""
import json
import re

import pytest

from job_rag import about
from job_rag.evaluate import questions_digest
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import client  # noqa: F401

RQS = [{"id": "r1", "question": "薪水多少？", "answerable": True, "gold": [{"file": "f", "heading": "h"}]},
       {"id": "r2", "question": "有員工餐廳嗎？", "answerable": False, "gold": []}]


def real_files(root, qs=RQS, digest=None):  # noqa: F811
    put(root, "eval/questions_real.json", {"questions": qs})
    put(root, "eval/results_real.json", {
        "digest": digest or questions_digest(qs), "n": 2, "n_answerable": 1, "n_unanswerable": 1, "n_cross": 1,
        "metrics": {"hit@1": 0.5, "hit@3": 0.75, "hit@5": 0.875, "mrr": 0.6},
        "gate_current": {"blocked_u": ["r2"], "passed_u": [], "blocked_a": []},
        "cross": [{"pass": True}, {"pass": False}]})


def test_real_eval_numbers_come_from_the_output_file(root):  # noqa: F811
    real_files(root)
    x = about._real_eval(root)
    assert (x["hit1"], x["hit5"], x["blocked_u"], x["blocked_a"], x["cross_passed"], x["cross_n"]) == (0.5, 0.875, 1, 0, 1, 2)


def test_real_eval_is_skipped_when_missing_or_stale(root):  # noqa: F811
    assert about._real_eval(root) is None                       # 沒有輸出檔
    real_files(root, digest="old")
    assert about._real_eval(root) is None                       # 題檔變了，輸出檔過期：不用舊數字
    real_files(root)
    (root / "eval/results_real.json").write_text("{壞掉", encoding="utf-8")
    assert about._real_eval(root) is None


def test_page_shows_real_line_and_generation_setting_note(client, root):  # noqa: F811
    real_files(root)
    html = client[1].get("/about?all=1").get_data(as_text=True)
    assert "另外 2 道真實問法" in html and "Hit@5 0.875" in html and "擋住 1/1" in html
    assert html.count("K=5 設定重跑") >= 2                # 細節與 RAGAS 說明都標註，並保留原數字


def test_page_without_real_output_has_no_real_line_but_keeps_note(client, root):  # noqa: F811
    html = client[1].get("/about?all=1").get_data(as_text=True)
    assert "真實問法" not in html and "K=5 設定重跑" in html


def test_blocked_case_uses_the_threshold_of_that_question():
    gate = {"threshold": 0.7, "thresholds": {"a": 0.62}, "answerable_blocked": ["a"], "unanswerable_blocked": [], "unanswerable_passed": []}
    m = {"ranks": {"a": 1}, "hit@1": 1, "hit@3": 1, "mrr": 1, "ci": {}, "gate": gate, "gate_scores": {"a": 0.6}}
    methods = {k: dict(m, gate=None) for k in about.METHODS} | {"bge-m3": m}
    table = [{"method": k, "mrr": 1.0} for k in about.METHODS]
    c = about._cases([{"id": "a", "question": "q", "gold": []}], methods, table)
    assert [x for x in c if x["kind"] == "blocked"][0]["threshold"] == 0.62


# ---- 與 repo 內已提交的輸出檔核對 ----
def test_committed_gate_numbers_match_results_methods_text():
    d = about.load()
    txt = (about.ROOT / "eval/results_methods.txt").read_text(encoding="utf-8")
    row = re.search(r"^bge-m3\s+\d+.*擋住 (\d+)/(\d+)\s+誤擋 (\d+)/(\d+)$", txt, re.M).groups()
    g = d["gate"]
    assert row == tuple(map(str, (g["unanswerable_blocked"], g["n_unanswerable"], g["answerable_blocked"], g["n_answerable"])))


def test_committed_real_numbers_match_results_real_text():
    x = about._real_eval(about.ROOT)
    assert x is not None, "eval/results_real.json 與 questions_real.json 對不上，請重跑 eval/run_real.py"
    txt = (about.ROOT / "eval/results_real.txt").read_text(encoding="utf-8")
    want = re.search(r"Hit@1 (\d\.\d{3}) \[.*?Hit@3 (\d\.\d{3}) \[.*?Hit@5 (\d\.\d{3}) \[.*?MRR (\d\.\d{3}) \[", txt).groups()
    assert want == tuple(f"{x[k]:.3f}" for k in ("hit1", "hit3", "hit5", "mrr"))
    cur = re.search(r"現在的設定.*?不可回答題擋住 (\d+)/(\d+).*?可回答題誤擋 (\d+)/(\d+)", txt).groups()
    assert cur == tuple(map(str, (x["blocked_u"], x["n_unanswerable"], x["blocked_a"], x["n_answerable"])))


def test_committed_real_questions_are_pending_and_have_no_private_markers():
    qs = json.loads((about.ROOT / "eval/questions_real.json").read_text(encoding="utf-8"))["questions"]
    assert len(qs) == 20 and all(q["status"].startswith("待使用者確認") for q in qs)
    assert sum(not q["answerable"] for q in qs) >= 5
    blob = json.dumps(qs, ensure_ascii=False)
    assert not any(w in blob for w in ("面試", "評價", "風險", "推測", "private"))

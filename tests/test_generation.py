"""生成層評估：流程用替身（搜尋、答案、評審）。不呼叫真 API。"""
import csv
import io
import json
import math
from pathlib import Path

import pytest

from job_rag import retrieval, search
from job_rag.answer import NOT_FOUND, AnswerError, answer, format_source
from job_rag.generation import (FAILED, GATED, SCORED, format_report, format_review, review_sample, run_eval,
                                summarize)
from tests.test_vector import FakeModel, fake_env  # noqa: F401  (autouse fixture)

MINI = Path(__file__).parent / "fixtures" / "mini"


def hit(n):
    return {"company": "甲", "file": "01_甲.md", "heading_path": f"段{n}", "text": f"內文{n}", "score": 0.9}


def qs(*specs):
    """specs: (id, answerable)"""
    return [{"id": i, "question": f"問題{i}", "answerable": a} for i, a in specs]


def run(questions, hits_by_id=None, ans=None, score=None):
    hits_by_id = hits_by_id or {}
    calls = {"answer": [], "score": []}

    def s(question, **kw):
        qid = question.removeprefix("問題")
        return hits_by_id.get(qid, [hit(1), hit(2)])

    def a(question, hits):
        calls["answer"].append(question)
        r = ans(question, hits) if ans else "答案 [1]"
        if isinstance(r, Exception):
            raise r
        return {"answer": r, "sources": []}

    def sc(question, text, contexts):
        calls["score"].append((question, text, contexts))
        r = score(question, text, contexts) if score else {"faithfulness": 0.5, "answer_relevancy": 0.8}
        if isinstance(r, Exception):
            raise r
        return r

    return run_eval(questions, s, a, sc), calls


# ---- 查無不呼叫 LLM ----
def test_gated_question_calls_neither_generation_nor_judge():
    rows, calls = run(qs(("a1", True)), hits_by_id={"a1": []})
    assert rows[0]["status"] == GATED
    assert rows[0]["faithfulness"] is None and rows[0]["answer_relevancy"] is None
    assert calls == {"answer": [], "score": []}


def test_model_replying_not_found_is_not_scored_and_not_filled_with_default():
    rows, calls = run(qs(("a1", True)), ans=lambda q, h: NOT_FOUND)
    assert rows[0]["status"] == "生成回查無"
    assert rows[0]["faithfulness"] is None
    assert calls["score"] == []


# ---- contexts 來自檢索結果 ----
def test_contexts_are_exactly_the_retrieved_paragraph_texts():
    hits = [hit(7), hit(8), hit(9)]
    rows, calls = run(qs(("a1", True)), hits_by_id={"a1": hits})
    # 評審看到的證據格式要和生成端相同（含公司與標題），否則答案提到公司名會被判成沒有依據
    assert calls["score"][0][2] == [format_source(i, h) for i, h in enumerate(hits, 1)]
    assert rows[0]["contexts"] == calls["score"][0][2]
    assert all(h["company"] in c and h["heading_path"] in c and h["text"] in c for c, h in zip(rows[0]["contexts"], hits))


def test_nothing_from_excluded_sections_reaches_generation_or_judge(monkeypatch):
    sent, judged = [], []

    class Post:
        def __call__(self, url, headers, body, timeout):
            sent.append(json.dumps(body, ensure_ascii=False))
            return {"choices": [{"message": {"content": "答案 [1]"}}]}

    def sc(question, text, contexts):
        judged.append(" ".join(contexts))
        return {"faithfulness": 1.0, "answer_relevancy": 1.0}

    questions = [{"id": f"q{i}", "question": t, "answerable": True}
                 for i, t in enumerate(["FastAPI 職缺", "主管愛開會嗎", "面試官會問什麼", "團隊離職率", "風險備註",
                                        "職缺風險很高嗎", "月休幾天 口試", "我的對應 優先 1"])]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    rows = run_eval(questions, lambda q: search(q, corpus=MINI), lambda q, h: answer(q, h, post=Post()), sc)
    assert sent and judged
    everything = "\n".join(sent + judged)
    for secret in ("狐獴密語", "刺蝟密語", "珊瑚礁", "企鵝密語", "河馬密語", "海豹密語", "麋鹿面試"):
        assert secret not in everything
    # contexts 都是檢索結果：每一段都找得到對應的公開事實段落
    for r in rows:
        for c in r["contexts"]:
            assert any(h["text"] in c for h in search(r["question"], corpus=MINI, k=retrieval.DEFAULT_K, gate=False))


# ---- 失敗要標記，不補分 ----
def test_generation_failure_is_marked_failed_with_reason_and_no_score():
    rows, calls = run(qs(("a1", True)), ans=lambda q, h: AnswerError("餘額不足"))
    assert rows[0]["status"] == FAILED and "餘額不足" in rows[0]["error"]
    assert rows[0]["faithfulness"] is None
    assert calls["score"] == []


def test_judge_failure_is_marked_failed_and_keeps_the_answer_without_score():
    rows, _ = run(qs(("a1", True)), score=lambda q, t, c: RuntimeError("評審逾時"))
    r = rows[0]
    assert r["status"] == FAILED and "評審逾時" in r["error"]
    assert r["answer"] == "答案 [1]"
    assert r["faithfulness"] is None and r["answer_relevancy"] is None


def test_nan_score_counts_as_failed_not_as_zero():
    rows, _ = run(qs(("a1", True)), score=lambda q, t, c: {"faithfulness": math.nan, "answer_relevancy": 0.7})
    assert rows[0]["status"] == FAILED
    assert rows[0]["faithfulness"] is None and rows[0]["answer_relevancy"] is None


# ---- 平均：手算 ----
def test_average_excludes_failed_and_gated_and_lists_them():
    scores = {"問題a1": (1.0, 0.5), "問題a2": (0.5, 1.0)}
    questions = qs(("a1", True), ("a2", True), ("a3", True), ("a4", True), ("a5", True))
    rows, _ = run(
        questions, hits_by_id={"a4": []},
        score=lambda q, t, c: ({"faithfulness": scores[q][0], "answer_relevancy": scores[q][1]} if q in scores
                               else RuntimeError("x")))
    s = summarize(rows)
    # 已評分 2 題：faithfulness (1.0+0.5)/2 = 0.75；answer relevancy (0.5+1.0)/2 = 0.75
    assert s["answerable"] == {"n": 5, "scored": 2, "failed": ["a3", "a5"], "gated": ["a4"], "model_not_found": []}
    assert s["faithfulness"] == pytest.approx(0.75)
    assert s["answer_relevancy"] == pytest.approx(0.75)


def test_average_is_none_when_nothing_scored():
    rows, _ = run(qs(("a1", True)), hits_by_id={"a1": []})
    s = summarize(rows)
    assert s["faithfulness"] is None and s["answer_relevancy"] is None


# ---- 不可回答題：只報拒答比例，不計分、不進平均 ----
def test_unanswerable_reports_refusal_rate_and_never_enters_averages():
    questions = qs(("a1", True), ("u1", False), ("u2", False), ("u3", False))
    rows, calls = run(questions, hits_by_id={"u1": []}, ans=lambda q, h: NOT_FOUND if q == "問題u2" else "亂答 [1]")
    s = summarize(rows)
    # u1 被門檻擋、u2 模型回查無、u3 亂答 → 拒答 2/3
    assert s["unanswerable"] == {"n": 3, "refused": 2, "failed": []}
    assert s["faithfulness"] == pytest.approx(0.5)  # 只有 a1
    assert [c[0] for c in calls["score"]] == ["問題a1"]


def test_unanswerable_api_failure_is_listed_not_counted_as_refusal():
    rows, _ = run(qs(("u1", False)), ans=lambda q, h: AnswerError("斷線"))
    assert summarize(rows)["unanswerable"] == {"n": 1, "refused": 0, "failed": ["u1"]}


# ---- 報告 ----
def test_report_lists_every_answerable_question_and_the_gated_ones_separately():
    rows, _ = run(qs(("a1", True), ("a2", True), ("u1", False)), hits_by_id={"a2": []})
    text = format_report(rows)
    assert "a1" in text and "0.500" in text and "0.800" in text
    assert "被查無門檻擋住" in text and "沒有被打分" in text and "a2" in text
    assert "自我偏好" in text and "題數少" in text


# ---- 人工抽查：可重現 ----
def many(n=20):
    rows, _ = run(qs(*[(f"a{i:02d}", True) for i in range(n)]), hits_by_id={"a03": []},
                  ans=lambda q, h: NOT_FOUND if q == "問題a05" else f"答案{q}")
    return rows


def test_sample_is_reproducible_and_only_from_questions_with_generated_answers():
    rows = many()
    a, b = review_sample(rows, 10, seed=0), review_sample(list(reversed(rows)), 10, seed=0)
    assert [r["id"] for r in a] == [r["id"] for r in b]       # 與輸入順序無關
    assert len(a) == 10 and len({r["id"] for r in a}) == 10
    assert not {"a03", "a05"} & {r["id"] for r in a}           # 被擋、回查無的不抽
    assert [r["id"] for r in review_sample(rows, 10, seed=1)] != [r["id"] for r in a]


def test_sample_takes_all_when_fewer_than_n():
    assert len(review_sample(many(4), 10)) == 3  # a03 被擋


def test_review_sheet_has_required_columns_and_empty_judgement_column():
    sample = review_sample(many(), 10, seed=0)
    rows = list(csv.reader(io.StringIO(format_review(sample))))
    assert rows[0] == ["題號", "問題", "答案", "引用段落", "是否忠於出處（使用者填）"]
    assert len(rows) == 11
    assert all(r[4] == "" for r in rows[1:])
    assert "內文1" in rows[1][3]


# ---- 乾跑估算：手算呼叫數 ----
def test_estimate_counts_calls_by_hand_and_skips_gated_questions():
    from job_rag.generation import estimate
    questions = qs(("a1", True), ("a2", True), ("a3", True), ("u1", False), ("u2", False))
    hits = {"a3": [], "u2": []}
    e = estimate(questions, lambda q: hits.get(q.removeprefix("問題"), [hit(1)]))
    # 擋住 a3、u2；生成 a1 a2 u1 = 3 次；評審只對可回答且放行的 a1 a2：2 題 × (2+3) = 10 次
    assert (e["gated"], e["generation_calls"], e["judge_calls"]) == (2, 3, 10)
    assert 0 < e["cost_usd"][0] < e["cost_usd"][1]

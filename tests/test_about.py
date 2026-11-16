"""專案說明頁：只測外部行為。輸出檔用 tmp_path 的小假檔，數字用手算。"""
import json

import pytest

from job_rag.evaluate import metrics, questions_digest, results_json

QS = [
    {"id": "a1", "question": "甲的資本額？", "answerable": True, "gold": [{"file": "01_甲.md", "heading": "1. 基本資料"}]},
    {"id": "a2", "question": "乙做什麼？", "answerable": True, "gold": [{"file": "02_乙.md", "heading": "2. 業務"}]},
    {"id": "u1", "question": "丙的董事長喜歡什麼？", "answerable": False, "gold": []},
]


def rep(ranks, gate=None):
    sc = {"ranks": ranks, "metrics": metrics(list(ranks.values())), "gate_scores": None, "unanswerable": {"n": 1}}
    if gate:
        sc |= {"gate": gate, "gate_scores": {"a1": 0.9, "a2": 0.6, "u1": 0.5}}
    return {"scores": sc}


def test_results_json_has_hand_counted_numbers_and_ranks():
    gate = {"threshold": 0.7, "answerable_blocked": ["a2"], "unanswerable_blocked": ["u1"], "unanswerable_passed": []}
    out = results_json(QS, {"bm25": rep({"a1": None, "a2": 2}), "bge-m3": rep({"a1": 1, "a2": 4}, gate)})
    assert out["digest"] == questions_digest(QS)
    assert (out["n_answerable"], out["n_unanswerable"]) == (2, 1)
    b = out["methods"]["bm25"]
    assert (b["hit@1"], b["hit@3"], b["mrr"]) == (0.0, 0.5, 0.25)  # a1 沒找到、a2 第 2 名
    assert b["ranks"] == {"a1": None, "a2": 2} and b["gate"] is None
    assert len(b["ci"]["mrr"]) == 2
    m = out["methods"]["bge-m3"]
    assert (m["hit@1"], m["mrr"]) == (0.5, 0.625)  # (1 + 1/4) / 2
    assert m["gate"]["answerable_blocked"] == ["a2"] and m["gate"]["threshold"] == 0.7
    json.dumps(out)  # 能寫成 JSON


def test_digest_changes_when_a_question_changes():
    other = [dict(QS[0], question="甲的資本額是多少？")] + QS[1:]
    assert questions_digest(QS) != questions_digest(other)
    assert questions_digest(QS) == questions_digest([dict(q) for q in QS])

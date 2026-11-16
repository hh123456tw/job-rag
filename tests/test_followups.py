"""票 22：追問題迷你評估的計分。小語料、BM25、手算名次。"""
import json

import pytest

from job_rag import followups
from job_rag.evalset import PENDING, verify
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

GOLD = [{"file": "01_甲科技.md", "heading": "4. 職缺（後端） > 4.1 薪資範圍", "quote": "月薪四萬到六萬"}]
Q1 = {"id": "f1", "company": "甲科技", "previous": "甲科技有哪些職缺？", "question": "那薪水呢？", "type": "追問", "answerable": True,
      "gold": GOLD, "status": PENDING}
Q2 = {"id": "f2", "company": "甲科技", "previous": "甲科技是做什麼的？", "question": "甲科技有哪些職缺？", "type": "追問",
      "answerable": True, "gold": GOLD, "status": PENDING}  # 自帶公司名與主題詞：規則不補全，兩種做法同一問句


def test_gold_quote_is_checked_against_the_corpus():
    assert verify([Q1], corpus=MINI) == []
    bad = dict(Q1, gold=[dict(GOLD[0], quote="年薪百萬")])
    assert any("引文不在金標標題之下" in p for p in verify([bad], corpus=MINI))


def test_both_modes_are_scored_and_only_rule_matches_are_completed():
    r = followups.run([Q1, Q2], method="bm25", corpus=MINI)
    assert r["n"] == 2 and r["expanded_ids"] == ["f1"]
    assert r["no_expand"]["ranks"]["f2"] == r["expand"]["ranks"]["f2"]  # 不補全的題，兩種做法結果相同
    assert r["expand"]["ranks"]["f1"] is not None and r["expand"]["ranks"]["f1"] <= 3  # 補全後找得到（甲科技、職缺都在問句裡）


def test_found_counts_are_integers_and_hit_at_3_is_their_ratio():
    r = followups.run([Q1, Q2], method="bm25", corpus=MINI)
    for m in ("no_expand", "expand"):
        ranks = r[m]["ranks"].values()
        assert r[m]["found"] == sum(x is not None and x <= 3 for x in ranks) and r[m]["hit@3"] == r[m]["found"] / 2


def test_digest_changes_when_a_question_or_gold_changes():
    base = followups.digest([Q1])
    assert followups.digest([dict(Q1, previous="x")]) != base and followups.digest([dict(Q1, gold=[])]) != base
    assert followups.digest(json.loads(json.dumps([Q1]))) == base

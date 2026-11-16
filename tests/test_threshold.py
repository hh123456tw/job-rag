"""查無門檻：最高分低於門檻就回查無。挑門檻與信賴區間用手算小例子驗證；搜尋端用假嵌入器。"""
import inspect
from pathlib import Path

import pytest

from job_rag import retrieval, search
from job_rag.stats import gate_outcome, paired_diff_interval, pick_threshold, mrr_interval, verdict
from tests.test_vector import FakeModel, fake_env  # noqa: F401  (autouse fixture)

MINI = Path(__file__).parent / "fixtures" / "mini"


# ---- 挑門檻：手算（可回答放行率 + 不可回答擋住率，取最高）----
def test_pick_threshold_without_tie():
    # 可回答 .6 .7；不可回答 .2 .3。候選＝相鄰分數中點 .25 .45 .65
    # .25：放行 2/2 + 擋住 1/2 = 1.5；.45：1 + 1 = 2；.65：1/2 + 1 = 1.5。選 .45
    assert pick_threshold([0.6, 0.7], [0.2, 0.3]) == pytest.approx(0.45)


def test_pick_threshold_tie_takes_lowest_so_fewer_answerable_are_blocked():
    # 可回答 .6 .7 .8；不可回答 .3 .5 .65。候選 .4 .55 .625 .675 .75
    # 分數 = 放行率 + 擋住率：4/3 5/3 4/3 5/3 4/3。.55 與 .675 同分，取較低的 .55
    assert pick_threshold([0.6, 0.7, 0.8], [0.3, 0.5, 0.65]) == pytest.approx(0.55)


def test_pick_threshold_does_not_force_all_unanswerable_blocked():
    # 一題不可回答分數（.9）比所有可回答題都高：要擋它就得擋掉全部可回答題，所以不擋它
    # 候選 .45 .65 .75 .85 → .45：1+1/2；.65：2/3+1/2；.75：1/3+1/2；.85：0+1/2。選 .45，可回答題全放行
    assert pick_threshold([0.6, 0.7, 0.8], [0.3, 0.9]) == pytest.approx(0.45)


def test_pick_threshold_needs_both_kinds_of_questions():
    with pytest.raises(ValueError):
        pick_threshold([0.6], [])


# ---- 門檻邊界：分數等於門檻放行，低於才擋 ----
def test_gate_outcome_boundary_and_hand_counts():
    out = gate_outcome({"a": 0.6, "b": 0.4}, {"u": 0.5, "v": 0.2}, 0.5)
    assert out["answerable_blocked"] == ["b"]      # .4 < .5
    assert out["unanswerable_blocked"] == ["v"]    # .2 < .5；u 剛好 .5，放行（沒擋住）
    assert out["unanswerable_passed"] == ["u"]


# ---- bootstrap：1000 次重抽、固定種子 ----
def test_interval_two_questions_hand_worked():
    # 排名 [1, 未命中] → 倒數名次 [1, 0]。重抽 2 題，平均只可能 0（1/4）、0.5（1/2）、1（1/4）
    # 2.5% 位置落在 0，97.5% 位置落在 1
    assert mrr_interval([1, None]) == (0.0, 1.0)
    # 排名 [1, 2] → [1, .5]：平均 .5（1/4）、.75（1/2）、1（1/4）
    assert mrr_interval([1, 2]) == (0.5, 1.0)


def test_interval_is_reproducible_with_fixed_seed_and_depends_on_seed():
    ranks = [1, 2, None, 3, 1, 5, None, 1]
    assert mrr_interval(ranks) == mrr_interval(ranks)
    assert mrr_interval(ranks, seed=1) != mrr_interval(ranks, seed=2)


def test_paired_diff_constant_gap_has_zero_width():
    # 每題 A 都是 1 名（1）、B 都是 2 名（.5）：差 .5 不論怎麼抽
    assert paired_diff_interval([1, 1, 1], [2, 2, 2]) == (0.5, 0.5)


def test_paired_diff_uses_the_same_resample_for_both_methods():
    # A=[1,None]、B=[None,1]：逐題差 [+1,-1]。同一次重抽平均差 ∈ {-1, 0, 1}，機率 1/4、1/2、1/4
    # 若 A、B 各自重抽，差的分佈會不同；配對時一定是 (-1, 1)
    assert paired_diff_interval([1, None], [None, 1]) == (-1.0, 1.0)


def test_identical_methods_have_zero_difference():
    assert paired_diff_interval([1, 2, None], [1, 2, None]) == (0.0, 0.0)


def test_verdict_plain_words():
    assert "差異可信" in verdict((0.05, 0.2))
    assert "差異可信" in verdict((-0.3, -0.1))              # 全為負也是真的有差
    assert "不能" in verdict((-0.02, 0.1))              # 區間含 0
    assert "不能" in verdict((0.0, 0.1))                # 剛好碰到 0 也不算


# ---- search()：預設與查無 ----
def test_default_method_is_bge_m3():
    assert inspect.signature(search).parameters["method"].default == "bge-m3"


def _top(question, **kw):
    return retrieval.gate_score(question, corpus=MINI, **kw)


def test_below_threshold_returns_nothing_for_bge_m3_and_hybrid(monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    assert search("鯨魚追蹤軟體", corpus=MINI) == []
    assert search("鯨魚追蹤軟體", method="hybrid", corpus=MINI) == []


def test_score_equal_to_threshold_is_not_blocked(monkeypatch):
    s = _top("鯨魚追蹤軟體", method="bge-m3")
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", s)
    assert search("鯨魚追蹤軟體", corpus=MINI)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", s + 1e-6)
    assert search("鯨魚追蹤軟體", corpus=MINI) == []


def test_methods_without_threshold_are_not_blocked(monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    for m in ("bm25", "bge-small-zh", "e5-large"):
        assert search("鯨魚追蹤軟體", method=m, corpus=MINI), m
        assert _top("鯨魚追蹤軟體", method=m) is None


def test_hybrid_is_gated_by_the_bge_m3_top_score_not_the_rrf_score(monkeypatch):
    assert _top("鯨魚追蹤軟體", method="hybrid") == _top("鯨魚追蹤軟體", method="bge-m3")
    r = search("鯨魚追蹤軟體", method="hybrid", corpus=MINI, gate=False)
    assert r[0]["score"] < 0.1  # RRF 分數（≤ 2/61）：名次分數，不能拿來比門檻


def test_gate_false_skips_the_threshold(monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)
    assert search("鯨魚追蹤軟體", corpus=MINI, gate=False)

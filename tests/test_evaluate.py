"""評分器：指標用手算例子；金標比對含負向案例。檢索只透過 search()。"""
import pytest

from job_rag.evaluate import hit_rank, metrics

G = [{"file": "01_甲.md", "heading": "4. 職缺"}]


def r(file, heading):
    return {"file": file, "heading_path": heading}


def test_hit_rank_is_one_based_position_of_first_gold():
    res = [r("01_甲.md", "5. 技術堆疊"), r("01_甲.md", "4. 職缺")]
    assert hit_rank(res, G) == 2


def test_subheading_under_gold_counts_as_hit():
    assert hit_rank([r("01_甲.md", "4. 職缺 > 4.1 薪資")], G) == 1


def test_any_of_several_golds_counts():
    golds = G + [{"file": "02_乙.md", "heading": "5. 技術堆疊"}]
    assert hit_rank([r("x.md", "a"), r("02_乙.md", "5. 技術堆疊")], golds) == 2


def test_no_gold_in_results_is_none():
    assert hit_rank([r("01_甲.md", "5. 技術堆疊")], G) is None
    assert hit_rank([], G) is None


@pytest.mark.parametrize("heading", [
    "4. 職缺風險",          # 名稱相近：前綴字串相同但不是同一標題
    "4. 職缺（後端）",
    "4. 職缺2 > 子標題",
    "9. 4. 職缺",           # 標題中段含有金標名稱
])
def test_similar_but_different_heading_is_not_hit(heading):
    assert hit_rank([r("01_甲.md", heading)], G) is None


def test_same_heading_in_other_file_is_not_hit():
    assert hit_rank([r("02_乙.md", "4. 職缺")], G) is None


def test_metrics_hand_worked_example():
    # 排名 1、2、未命中、3：Hit@1=1/4，Hit@3=3/4，MRR=(1+1/2+0+1/3)/4=11/24
    m = metrics([1, 2, None, 3])
    assert m["n"] == 4
    assert m["hit@1"] == 0.25
    assert m["hit@3"] == 0.75
    assert m["mrr"] == pytest.approx(11 / 24)


def test_rank_four_is_not_hit_at_3_but_counts_in_mrr():
    m = metrics([4])
    assert m["hit@3"] == 0 and m["mrr"] == 0.25


def test_metrics_without_questions_raises_not_zero():
    with pytest.raises(ValueError):
        metrics([])


# ---- evaluate()：經 search() 對 tests/fixtures/mini 評分 ----
from pathlib import Path

from job_rag.evaluate import evaluate, format_report

MINI = Path(__file__).parent / "fixtures" / "mini"


def Q(id, question, gold=None):
    return {"id": id, "question": question, "answerable": gold is not None,
            "gold": [{"file": f, "heading": h} for f, h in (gold or [])]}


QS = [
    Q("q1", "鯨魚追蹤軟體", [("01_甲科技.md", "1. 基本資料")]),
    Q("q2", "刺蝟密語", [("02_乙資訊.md", "7. 工作評價")]),  # 金標在排除段落：公開池搜不到
    Q("q3", "zzzxqv qqq 量子麵包"),
]


def test_scores_cover_all_answerable_questions_over_public_pool_only():
    rep = evaluate(QS, corpus=MINI)
    assert rep["scores"]["ranks"] == {"q1": 1, "q2": None}
    assert rep["scores"]["metrics"]["n"] == 2
    assert "query_private" not in rep and "query" not in rep


def test_report_has_no_private_only_row():
    out = format_report(evaluate(QS, corpus=MINI))
    assert "私人" not in out and "查詢模式" not in out and "演示模式" not in out


def test_excluded_section_is_not_searchable_so_its_question_misses():
    from job_rag import search
    assert search("刺蝟密語", mode="demo", corpus=MINI) == []


def test_unanswerable_refusal_rate_is_not_invented():
    rep = evaluate(QS, corpus=MINI)
    assert rep["scores"]["unanswerable"] == {"n": 1, "refusal_rate": None}
    assert "尚未實作門檻" in format_report(rep)


def test_wrong_gold_gives_miss_not_error():
    rep = evaluate([Q("q9", "鯨魚追蹤軟體", [("01_甲科技.md", "2. 業務與財務")])], corpus=MINI)
    assert rep["scores"]["ranks"] == {"q9": None}
    assert rep["scores"]["metrics"]["hit@3"] == 0


def test_questions_without_answerable_gives_no_metrics():
    rep = evaluate([QS[2]], corpus=MINI)
    assert rep["scores"]["metrics"] is None

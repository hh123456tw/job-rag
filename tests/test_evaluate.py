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
    rep = evaluate(QS, method="bm25", corpus=MINI)
    assert rep["scores"]["ranks"] == {"q1": 1, "q2": None}
    assert rep["scores"]["metrics"]["n"] == 2
    assert "query_private" not in rep and "query" not in rep


def test_report_has_no_private_only_row():
    out = format_report(evaluate(QS, method="bm25", corpus=MINI))
    assert "私人" not in out and "查詢模式" not in out and "演示模式" not in out


def test_excluded_section_is_not_searchable_so_its_question_misses():
    from job_rag import search
    assert search("刺蝟密語", corpus=MINI, method="bm25") == []


def test_method_without_threshold_has_no_refusal_rate_and_says_so():
    rep = evaluate(QS, method="bm25", corpus=MINI)
    assert rep["scores"]["unanswerable"] == {"n": 1, "refusal_rate": None}
    assert "沒做查無門檻" in format_report(rep)


def test_wrong_gold_gives_miss_not_error():
    rep = evaluate([Q("q9", "鯨魚追蹤軟體", [("01_甲科技.md", "2. 業務與財務")])], method="bm25", corpus=MINI)
    assert rep["scores"]["ranks"] == {"q9": None}
    assert rep["scores"]["metrics"]["hit@3"] == 0


def test_questions_without_answerable_gives_no_metrics():
    rep = evaluate([QS[2]], method="bm25", corpus=MINI)
    assert rep["scores"]["metrics"] is None


# ---- 題型分組 ----
def test_scores_are_grouped_by_question_type():
    qs = [Q("a", "鯨魚追蹤軟體", [("01_甲科技.md", "1. 基本資料")]) | {"type": "單一公司"},
          Q("b", "刺蝟密語", [("02_乙資訊.md", "7. 工作評價")]) | {"type": "職缺"},
          Q("c", "量子麵包 zzzxqv") | {"type": "不可回答"}]
    rep = evaluate(qs, method="bm25", corpus=MINI)
    assert rep["by_type"]["單一公司"]["n"] == 1 and rep["by_type"]["單一公司"]["hit@1"] == 1
    assert rep["by_type"]["職缺"]["hit@3"] == 0
    assert "不可回答" not in rep["by_type"]  # 不可回答題不計 Hit@k / MRR
    out = format_report(rep)
    assert "單一公司" in out and "職缺" in out


# ---- 5 種方式並列（票 03）----
from job_rag.evaluate import compare, format_table, SUSPICIOUS


def _fake_models(monkeypatch, tmp_path):
    from tests.test_vector import FakeModel
    from job_rag import retrieval
    monkeypatch.setenv("JOB_RAG_CACHE", str(tmp_path))
    monkeypatch.setattr(retrieval, "_load_model", lambda m: FakeModel(m))
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.0)
    for f in (retrieval._parse, retrieval._public, retrieval._bm25, retrieval._index):
        f.cache_clear()


def test_compare_runs_all_five_methods_and_table_lists_each(monkeypatch, tmp_path):
    _fake_models(monkeypatch, tmp_path)
    reps = compare(QS, corpus=MINI)
    assert list(reps) == ["bm25", "bge-small-zh", "bge-m3", "e5-large", "hybrid"]
    t = format_table(reps)
    for m in reps:
        assert m in t
    for head in ("Hit@1", "Hit@3", "MRR"):
        assert head in t
    assert "私人" not in t and "查詢模式" not in t


def _rep(h1, h3, mrr):
    g = {"ranks": {}, "metrics": {"n": 10, "hit@1": h1, "hit@3": h3, "mrr": mrr}, "unanswerable": {"n": 0, "refusal_rate": None}}
    return {"method": "x", "scores": g}


def test_near_perfect_score_is_flagged_suspicious():
    assert SUSPICIOUS in format_table({"bm25": _rep(1.0, 1.0, 1.0)})
    assert SUSPICIOUS in format_table({"bm25": _rep(0.9, 0.96, 0.93)})


def test_ordinary_scores_are_not_flagged():
    assert SUSPICIOUS not in format_table({"bm25": _rep(0.6, 0.8, 0.7)})


# ---- 票 04：查無、信賴區間、面試行過濾寫進輸出 ----
from job_rag import interview_drops, retrieval
from job_rag.evaluate import format_results


def test_gated_method_reports_refusal_and_false_blocks(monkeypatch, tmp_path):
    _fake_models(monkeypatch, tmp_path)
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)  # 全部擋住
    g = evaluate(QS, method="bge-m3", corpus=MINI)["scores"]
    assert g["unanswerable"]["refusal_rate"] == 1.0           # q3 被擋住
    assert g["gate"]["answerable_blocked"] == ["q1", "q2"]    # 兩題可回答題也被誤擋
    assert g["ranks"]["q1"] == 1                              # 排名不套門檻
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", -1.0)  # 全部放行
    g = evaluate(QS, method="bge-m3", corpus=MINI)["scores"]
    assert g["unanswerable"]["refusal_rate"] == 0.0 and g["gate"]["answerable_blocked"] == []


def test_results_text_has_threshold_interval_and_interview_sections(monkeypatch, tmp_path):
    _fake_models(monkeypatch, tmp_path)
    reps = compare(QS, corpus=MINI)
    text = format_results(QS, reps, interview_drops(MINI))
    for need in ("95% 區間", "bge-m3 減 hybrid", "同一批", "沒有獨立測試題", "沒做門檻",
                 "丟掉", "誤丟風險", "麋鹿面試"):
        assert need in text, need
    assert "AI 協作" not in text


def test_table_rows_show_interval_only_for_methods_with_questions():
    t = format_table({"bm25": _rep(0.6, 0.8, 0.7)})
    assert "沒做門檻" in t and "（無）" not in t


def _d(file, line, public=True):
    return {"file": file, "heading_path": "4. 職缺", "line": line, "public": public}


def test_interview_report_buckets_by_hand_counted_example():
    from job_rag.evaluate import format_interview
    drops = [_d("01_甲.md", "- GoodJob 面試心得有 AI 工程師"),               # 第三方
             _d("A_104.md", "- 其他條件：持有證書者優先面試"),                  # 104 職缺檔：最可能誤丟職缺內容
             _d("A_104.md", "| 資料工程師 | 面試：筆試 |"),
             _d("01_甲.md", "- 面試時必問：駐點地點"),                         # 其他（提醒語）
             _d("01_甲.md", "- 面試官提問……", public=False)]                 # 排除段落：不算
    out = format_interview(drops)
    assert "丟掉 5 行；其中在公開事實段落內 4 行，其餘 1 行" in out
    assert "第三方面試心得或面試網站 1 行" in out
    assert "104 職缺檔 2 行" in out and "其他 1 行" in out
    assert "優先面試" in out and "面試官提問" not in out  # 104 的行逐行列出；排除段落的不列


def test_gate_report_shows_how_close_the_nearest_questions_are(monkeypatch):
    from job_rag.evaluate import format_gate
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.45)
    qs = [Q("a", "x", [("f", "h")]), Q("b", "x", [("f", "h")]), Q("u", "x")]
    rep = {"bge-m3": {"scores": {"gate_scores": {"a": 0.8, "b": 0.5, "u": 0.4},
                                 "metrics": {"n": 2}, "unanswerable": {"n": 1},
                                 "gate": {"unanswerable_blocked": ["u"], "unanswerable_passed": [], "answerable_blocked": []}}}}
    out = format_gate(qs, rep)
    # 擋住的不可回答題最高分 .400；放行的可回答題最低分 .500（.8 離得遠，不列）
    assert "貼線" in out and "0.4000" in out and "0.5000" in out and "0.8000" not in out

"""專案說明頁的資料層：讀輸出檔、算頁面數字、挑失敗案例。輸出檔用 tmp_path 的小假檔，數字用手算。"""
import json

import pytest

from job_rag.about import AboutDataError, load
from job_rag.evaluate import metrics, results_json

QS4 = [
    {"id": "a1", "question": "甲的資本額？", "answerable": True, "gold": [{"file": "01_甲.md", "heading": "1. 基本資料"}]},
    {"id": "a2", "question": "乙做什麼？", "answerable": True, "gold": [{"file": "02_乙.md", "heading": "2. 業務"}]},
    {"id": "a3", "question": "丙有哪些職缺？", "answerable": True, "gold": [{"file": "03_丙.md", "heading": "4. 職缺"}]},
    {"id": "a4", "question": "丁用什麼技術？", "answerable": True, "gold": [{"file": "04_丁.md", "heading": "5. 技術"}]},
    {"id": "u1", "question": "戊的董事長喜歡什麼？", "answerable": False, "gold": []},
]
RANKS = {  # 方式 -> a1..a4 名次（None＝前 10 名沒有）
    "bm25": [None, 5, 1, 1], "bge-small-zh": [None, 1, 1, 1], "bge-m3": [1, 1, 1, 2],
    "e5-large": [4, 4, 1, 1], "hybrid": [3, 1, 1, 1]}
GATE = {"threshold": 0.7, "answerable_blocked": ["a3", "a4"], "unanswerable_blocked": ["u1"], "unanswerable_passed": []}


def methods_file(qs=QS4, ranks=RANKS, gate=GATE):
    reps = {}
    for m, rs in ranks.items():
        d = dict(zip(["a1", "a2", "a3", "a4"], rs))
        sc = {"ranks": d, "metrics": metrics(rs), "gate_scores": None, "unanswerable": {"n": 1}}
        if m == "bge-m3":
            sc |= {"gate": gate, "gate_scores": {"a1": 0.9, "a2": 0.8, "a3": 0.65, "a4": 0.69, "u1": 0.5}}
        reps[m] = {"scores": sc}
    return results_json(qs, reps)


def gen_rows(qs=QS4):
    st = {"a1": ("已評分", 1.0, 0.9), "a2": ("已評分", 1.0, 0.7), "a3": ("被查無門檻擋住", None, None),
          "a4": ("已評分", 0.5, 0.8), "u1": ("被查無門檻擋住", None, None)}
    return [{"id": q["id"], "question": q["question"], "answerable": q["answerable"], "status": st[q["id"]][0],
             "faithfulness": st[q["id"]][1], "answer_relevancy": st[q["id"]][2]} for q in qs]


def cross_rows():
    c = lambda ok: {"text": "x", "supported": ok, "evidence": "y"}
    return [{"id": "a1", "claims": [c(True), c(True)], "faithfulness": 1.0},
            {"id": "a2", "claims": [c(True)], "faithfulness": 1.0},
            {"id": "a4", "claims": [c(True), c(False)], "faithfulness": 0.5}]


def put(root, rel, obj):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    put(tmp_path, "eval/questions.json", {"questions": QS4})
    put(tmp_path, "eval/results_methods.json", methods_file())
    put(tmp_path, "eval/results_generation.json", gen_rows())
    put(tmp_path, "eval/crossjudge/judge_gpt.json", cross_rows())
    return tmp_path


def test_table_numbers_come_from_the_output_file(root):
    d = load(root)
    rows = {r["method"]: r for r in d["table"]}
    assert list(rows) == ["bm25", "bge-small-zh", "bge-m3", "e5-large", "hybrid"]
    b = rows["bm25"]  # 名次 無、5、1、1
    assert (b["hit@1"], b["hit@3"], b["mrr"]) == (0.5, 0.5, pytest.approx((0 + 1 / 5 + 1 + 1) / 4))
    assert rows["bge-m3"]["mrr"] == pytest.approx(0.875)
    lo, hi = rows["bge-m3"]["ci"]["mrr"]
    assert lo <= 0.875 <= hi
    assert d["n_answerable"] == 4 and d["n_unanswerable"] == 1


def test_generation_means_count_only_scored_questions(root):
    g = load(root)["generation"]
    assert g["scored"] == 3 and g["gated"] == 1 and g["failed"] == 0
    assert g["faithfulness"] == pytest.approx((1 + 1 + 0.5) / 3)
    assert g["answer_relevancy"] == pytest.approx((0.9 + 0.7 + 0.8) / 3)


def test_gate_line_numbers(root):
    g = load(root)["gate"]
    assert (g["unanswerable_blocked"], g["n_unanswerable"]) == (1, 1)
    assert (g["answerable_blocked"], g["n_answerable"]) == (2, 4)


def test_cross_judge_summary_and_consistency_rule(root):
    c = load(root)["cross"]
    assert (c["n"], c["claims"], c["supported"]) == (3, 5, 4)
    assert c["mean"] == pytest.approx(2.5 / 3) and c["consistent"] is True  # 與 RAGAS 平均 0.833 相同
    put(root, "eval/crossjudge/judge_gpt.json", [dict(r, faithfulness=1.0) for r in cross_rows()])
    assert load(root)["cross"]["consistent"] is False  # 1.0 與 0.833 差 0.167，不能說一致


@pytest.mark.parametrize("rel", ["eval/results_methods.json", "eval/results_generation.json", "eval/crossjudge/judge_gpt.json"])
def test_missing_output_file_is_a_clear_error_naming_the_file(root, rel):
    (root / rel).unlink()
    with pytest.raises(AboutDataError, match=rel.split("/")[-1]):
        load(root)


def test_unparseable_output_file_is_an_error_not_swallowed(root):
    put(root, "eval/results_generation.json", "{not json")
    with pytest.raises(AboutDataError, match="results_generation.json"):
        load(root)


def test_methods_output_for_an_older_question_set_is_rejected(root):
    qs = [dict(QS4[0], question="甲的資本額是多少？")] + QS4[1:]
    put(root, "eval/questions.json", {"questions": qs})
    with pytest.raises(AboutDataError, match="題組"):
        load(root)


def test_generation_output_for_an_older_question_set_is_rejected(root):
    put(root, "eval/results_generation.json", gen_rows()[:-1])  # 少一題
    with pytest.raises(AboutDataError, match="題組"):
        load(root)


def test_generation_scored_row_without_a_score_is_an_error(root):
    rows = gen_rows()
    rows[0]["faithfulness"] = None
    put(root, "eval/results_generation.json", rows)
    with pytest.raises(AboutDataError, match="a1"):
        load(root)


def test_cross_judge_ids_must_be_scored_questions(root):
    put(root, "eval/crossjudge/judge_gpt.json", cross_rows() + [{"id": "zz", "claims": [], "faithfulness": 1.0}])
    with pytest.raises(AboutDataError, match="zz"):
        load(root)


def test_method_missing_from_methods_output_is_an_error(root):
    m = methods_file()
    del m["methods"]["hybrid"]
    put(root, "eval/results_methods.json", m)
    with pytest.raises(AboutDataError, match="hybrid"):
        load(root)


def test_failure_cases_pick_rule(root):
    cases = load(root)["cases"]
    assert len(cases) == 2
    a, b = cases
    # a1：最好的方式（bge-m3，名次 1）找到；bm25、bge-small-zh、e5-large（名次 4）前 3 名沒有；hybrid 第 3 名算找到
    assert a["id"] == "a1" and a["kind"] == "miss" and a["failed_methods"] == ["bm25", "bge-small-zh", "e5-large"]
    # a4：被門檻誤擋的題裡，最高分最接近門檻（0.69 對 0.65）
    assert b["id"] == "a4" and b["kind"] == "blocked" and b["score"] == pytest.approx(0.69)


def test_a_question_the_best_method_also_misses_is_not_a_failure_case(root):
    ranks = dict(RANKS, **{"bge-m3": [None, 1, 1, 2], "hybrid": [None, 1, 1, 1], "e5-large": [None, 4, 1, 1]})
    put(root, "eval/results_methods.json", methods_file(ranks=ranks))
    miss = [c for c in load(root)["cases"] if c["kind"] == "miss"]
    assert all(c["id"] != "a1" for c in miss)


def test_cases_fill_up_to_two_and_never_invent(root):
    ranks = {m: [1, 1, 1, 1] for m in RANKS}  # 沒有任何方式差異
    put(root, "eval/results_methods.json", methods_file(ranks=ranks))
    assert [c["id"] for c in load(root)["cases"]] == ["a4", "a3"]  # 只剩門檻誤擋：最高分近的先
    put(root, "eval/results_methods.json", methods_file(ranks=ranks, gate=dict(GATE, answerable_blocked=[])))
    assert load(root)["cases"] == []


# ---- 公開版：沒有 DeepSeek 金鑰就沒有生成層輸出；兩個生成層檔都沒有時，只略過那一塊 ----
def test_without_any_generation_output_load_skips_that_block(root):
    (root / "eval/results_generation.json").unlink()
    (root / "eval/crossjudge/judge_gpt.json").unlink()
    d = load(root)
    assert d["generation"] is None and d["cross"] is None
    assert {r["method"]: r for r in d["table"]}["bge-m3"]["mrr"] == pytest.approx(0.875)  # 檢索成績照常


def test_questions_file_falls_back_to_the_sample_set(root):
    (root / "eval/questions.json").rename(root / "eval/questions.sample.json")
    assert load(root)["n_answerable"] == 4

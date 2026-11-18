"""票 41：獨立題 RAGAS 數字取自輸出檔；缺檔、壞檔、沒有有效分數就略過；負向：不把別的數字當獨立題數字。"""
import json

from job_rag import about
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import client  # noqa: F401

OUT = {"gated": ["h30", "h40"], "model_not_found": [],
       "stats": {"faithfulness": {"n": 23, "mean": 0.9125, "ci95": [0.85, 0.96]}, "answer_relevancy": {"n": 0, "mean": None, "ci95": None}}}


def put_gen(root, data):  # noqa: F811
    (root / "eval").mkdir(exist_ok=True)
    (root / "eval/results_heldout_generation.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_numbers_come_from_the_output_file_and_missing_answer_relevancy_stays_none(root):  # noqa: F811
    put_gen(root, OUT)
    h = about._heldout_gen(root)
    assert (h["n"], h["faithfulness"], h["answer_relevancy"], h["gated"], h["not_found"]) == (23, 0.9125, None, 2, 0)


def test_missing_broken_or_unscored_output_is_skipped(root):  # noqa: F811
    assert about._heldout_gen(root) is None
    (root / "eval").mkdir(exist_ok=True)
    (root / "eval/results_heldout_generation.json").write_text("{壞", encoding="utf-8")
    assert about._heldout_gen(root) is None
    put_gen(root, {**OUT, "stats": {**OUT["stats"], "faithfulness": {"n": 0, "mean": None, "ci95": None}}})
    assert about._heldout_gen(root) is None


def test_pages_show_the_held_line_with_self_judge_caveat_only_with_the_file(client, root):  # noqa: F811
    for url in ("/about", "/about?all=1"):
        assert "獨立題（現行設定" not in client[1].get(url).get_data(as_text=True)
    put_gen(root, OUT)
    for url in ("/about", "/about?all=1"):
        h = client[1].get(url).get_data(as_text=True)
        assert "獨立題（現行設定：K=5、補公司名）：忠實度 0.912（23 題）" in h and "可能偏樂觀" in h and "答案相關性 0." not in h.split("獨立題（現行設定")[1][:80]
        assert "K=5 設定重跑" in h


# ---- 獨立題的 GPT 複查：數字取自輸出檔；負向：題號不在獨立題內就不顯示 ----
def put_cross(root, rows):  # noqa: F811
    (root / "eval/crossjudge").mkdir(parents=True, exist_ok=True)
    (root / "eval/crossjudge/judge_gpt_heldout.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _claims(*flags):
    return [{"text": "x", "supported": f, "evidence": "e"} for f in flags]


def test_held_cross_counts_come_from_file_and_unknown_ids_are_rejected(root):  # noqa: F811
    put_gen(root, {**OUT, "per_question": [{"id": "h01"}, {"id": "h02"}]})
    assert about._heldout_cross(root) is None  # 沒有複查檔
    put_cross(root, [{"id": "h01", "claims": _claims(True, False, True), "faithfulness": 0.67}, {"id": "h02", "claims": _claims(True), "faithfulness": 1.0}])
    assert about._heldout_cross(root) == {"n": 2, "claims": 4, "supported": 3}
    put_cross(root, [{"id": "h99", "claims": _claims(True), "faithfulness": 1.0}])  # 不是已評分的獨立題
    assert about._heldout_cross(root) is None
    (root / "eval/crossjudge/judge_gpt_heldout.json").write_text("{壞", encoding="utf-8")
    assert about._heldout_cross(root) is None


def test_real_outputs_judge_files_match_scored_ids_and_page_text_is_not_stale():
    from pathlib import Path
    r = Path(about.ROOT)
    d = about.load(r)
    h = d["held_cross"]
    assert h and h["n"] == d["held_gen"]["n"]  # 獨立題每一題都複查過
    assert d["cross"]["n"] == d["generation"]["scored"]  # 題組每一題都複查過
    from job_rag.about_page import GEN_NOTE
    assert "沒有重跑" not in GEN_NOTE and "前一版語料" not in GEN_NOTE and "GPT 複查都於 2026-11-17～18" in GEN_NOTE


# ---- 票 43、44：獨立題上的 hybrid 與 reranker；沒有輸出檔就維持「沒量過」 ----
def test_held_methods_numbers_come_from_the_file_and_missing_file_keeps_not_measured(root):  # noqa: F811
    from job_rag.about_page import _hybrid_held, _rerank_line
    assert about._held_methods(root) is None and _rerank_line({"held_methods": None}) == ""
    m = lambda mrr, diff, lo, hi, sec: {"mrr": mrr, "sec_per_question": sec, "diff_vs_bge_m3": {"mrr": {"diff": diff, "ci": [lo, hi]}}}
    put(root, "eval/results_heldout_methods.json", {"n": 7, "cand": 20, "reranker": "rr-x", "methods": {
        "bge-m3": {"mrr": 0.8, "hit@1": 0.5}, "hybrid": m(0.7, -0.1, -0.2, -0.05, 0.1) | {"better": ["a"], "worse": ["b", "c"]},
        "rerank": m(0.85, 0.05, -0.01, 0.1, 6.6) | {"better": ["a", "b"], "worse": []}}, "ranks": {"bge-m3": {"a": 1, "b": 2, "c": None}}})
    h = about._held_methods(root)
    line = _rerank_line({"held_methods": h})
    assert "7 題" in line and "0.800 → 0.850" in line and "區間含 0，不能說有差" in line and "約 7 秒" in line and "rr-x" in line
    assert "區間不含 0，差異可信" in _hybrid_held({"held_methods": h})
    from job_rag.about_page import _hybrid_why, _rerank_why
    d = {"held_methods": h, "table": [{"method": "bm25", "mrr": 0.6}]}
    assert "變前 1 題、變後 2 題" in _hybrid_why(d) and "MRR 0.600" in _hybrid_why(d) and "推論" in _hybrid_why(d)
    w = _rerank_why(d, 9)
    assert "變前 2 題、變後 0 題" in w and "只有 2 題不是第 1 名" in w and "只有 9 段" in w and "推論" in w
    assert _hybrid_why({"held_methods": None}) == "" and _rerank_why({}, 9) == ""  # 沒有輸出檔：不寫原因
    put(root, "eval/results_heldout_methods.json", {"n": 7})  # 欄位不齊：不採用
    assert about._held_methods(root) is None

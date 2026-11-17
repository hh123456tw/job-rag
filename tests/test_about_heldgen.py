"""票 41：獨立題 RAGAS 數字取自輸出檔；缺檔、壞檔、沒有有效分數就略過；負向：不把別的數字當獨立題數字。"""
import json

from job_rag import about
from tests.test_about_data import root  # noqa: F401  (root 是 fixture)
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

"""票 40：切段上限掃描。腳本只暫時改常數、不碰 .cache/；/about 新句子的數字取自輸出檔，缺檔或過期就略過。"""
import sys
from pathlib import Path

import pytest

from job_rag import about, retrieval
from job_rag.about_page import _sweep_line
from job_rag.evaluate import questions_digest
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import client  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))
import run_chunk_sweep as sw  # noqa: E402

SAMPLE = str(retrieval.SAMPLE_CORPUS.resolve())


def test_overlap_is_15_percent_rounded():
    assert [sw.overlap_for(n) for n in sw.LENGTHS] == [60, 90, 135, 180]


def test_chunk_size_changes_segments_then_restores_constants_even_on_error():
    before = (retrieval.CHUNK, retrieval.OVERLAP)
    n_before = len(retrieval._segments(SAMPLE))
    with pytest.raises(RuntimeError):
        with sw.chunk_size(50):
            assert (retrieval.CHUNK, retrieval.OVERLAP) == (50, 8)
            assert len(retrieval._segments(SAMPLE)) > n_before  # 切得更碎
            raise RuntimeError("x")
    assert (retrieval.CHUNK, retrieval.OVERLAP) == before == (600, 90)
    assert len(retrieval._segments(SAMPLE)) == n_before          # 快取也還原


def test_cache_dir_is_never_the_project_cache(tmp_path):
    assert sw.cache_dir(tmp_path, 400).parent == tmp_path.resolve()
    with pytest.raises(RuntimeError):
        sw.cache_dir(sw.ROOT / ".cache", 400)


def seg(text, head="h", file="f"):
    return {"file": file, "heading_path": head, "text": text}


def pair(text, chunk=20, overlap=4):
    """用同一規則把 text 切段（與 retrieval._pieces 相同）。"""
    step = chunk - overlap
    return [seg(text[i:i + chunk]) for i in range(0, max(len(text) - overlap, 1), step)]


def test_url_cut_is_counted_and_lost_when_overlap_cannot_recover_it():
    t = "ab https://example.com/abcdef tail"  # 網址從第 3 字起，長 26，切在第 20 字
    c = sw.boundary_cuts(pair(t), 20, 4)
    assert (c["url_end_cut"], c["url_lost"], c["boundaries"]) == (1, 1, 1)


def test_url_followed_by_space_or_closing_paren_is_not_a_cut():
    for t in ("abcdefghi http://a.b tail words", "abcdefgh (http://a.b) tail words"):
        assert sw.boundary_cuts(pair(t), 20, 4)["url_end_cut"] == 0, t
    assert sw.boundary_cuts(pair("see http://x tail"), 20, 4)["boundaries"] == 0  # 只有一段：沒有接縫


def test_url_inside_overlap_is_cut_but_not_lost():
    t = "abcdefghijklmnop http://abcdefgh"  # 網址從第 17 字起，在下一段的重疊區（第 16 字起）內
    c = sw.boundary_cuts(pair(t), 20, 4)
    assert (c["url_end_cut"], c["url_lost"]) == (1, 0)


def test_table_row_cut_and_a_row_ending_exactly_at_the_boundary():
    assert sw.boundary_cuts(pair("|aa|bbbbbbbb|cccccc|dddd|"), 20, 4)["row_end_cut"] == 1  # 第 20 字落在列中間
    assert sw.boundary_cuts(pair("|aa|bbbbbbbbbbbb|cc|\n|dd|eeeeeeee|"), 20, 4)["row_end_cut"] == 0  # 剛好在列尾換行
    assert sw.boundary_cuts([seg("x" * 20), seg("y" * 20)], 20, 4)["boundaries"] == 0  # 不相連的兩段不算接縫


def test_gold_quote_split_between_chunks_is_not_intact_but_whole_or_near_miss_are_handled():
    g = [{"file": "f", "heading": "h", "quote": "年薪 81–108 萬"}]
    assert sw.gold_intact(g, [seg("xx 年薪 81–108 萬 yy")]) == [True]
    assert sw.gold_intact(g, [seg("xx 年薪 81–"), seg("108 萬 yy")]) == [False]   # 切在兩段之間
    assert sw.gold_intact(g, [seg("年薪 81–109 萬")]) == [False]                   # 差一個字
    assert sw.gold_intact(g, [seg("年薪 81–108 萬", head="其他")]) == [False]       # 別的標題底下不算
    assert sw.gold_intact(g, [seg("年薪 81–108 萬", head="h > 子")]) == [True]


def test_strict_rank_needs_the_quote_in_the_hit_chunk():
    g = [{"file": "f", "heading": "h", "quote": "八十一萬"}]
    res = [{"file": "f", "heading_path": "h", "text": "沒有數字"}, {"file": "f", "heading_path": "h", "text": "年薪八十一萬"}]
    assert sw.strict_rank(res, g) == 2   # 名次 1 在標題下但沒有引文：一般命中算 1，嚴格命中算 2
    assert sw.strict_rank(res[:1], g) is None


def test_conclusion_says_inside_interval_only_when_all_paired_diffs_include_zero():
    def mk(d3):
        pl = {str(n): {"pooled": {"metrics": {"hit@3": 0.8}, "ci": {"hit@3": [0.6, 0.95]}}} for n in (400, 600)}
        return {"per_length": pl, "paired_vs_base": {"400": {"hit@3": {"diff": d3[0], "ci": list(d3[1:])}, "mrr": {"diff": 0, "ci": [-0.1, 0.1]}}}}
    assert sw.conclude(mk((0.05, -0.1, 0.2)))["short"].startswith("差異在區間內")
    c = sw.conclude(mk((0.2, 0.05, 0.3)))
    assert not c["short"].startswith("差異在區間內") and c["significant"] == [[400, "hit@3"]]


QS = {"questions_real.json": [{"id": "r1", "question": "乙？", "answerable": True, "gold": []}],
      "questions_heldout.json": [{"id": "h1", "question": "丙？", "answerable": True, "gold": []}]}


def sweep_files(root, digest=None):  # noqa: F811
    from tests.test_about_data import QS4  # 舊 30 題檔沿用 root 已有的（改它會讓別的輸出檔過期）
    qs_all = {"questions.json": QS4} | QS
    keys = dict(zip(("old30", "real20", "held"), qs_all))
    for f, qs in QS.items():
        put(root, f"eval/{f}", {"questions": qs})
    put(root, "eval/results_chunk_sweep.json", {
        "digests": {k: (digest if digest and k == "real20" else questions_digest(qs_all[f])) for k, f in keys.items()},
        "per_length": {str(n): {"pooled": {"n": 40, "metrics": {"hit@3": h}}} for n, h in ((400, 0.75), (600, 0.8), (900, 0.8), (1200, 0.7))},
        "conclusion": {"short": "差異在區間內：測試句"}})


def test_sweep_numbers_come_from_the_file_and_missing_or_stale_returns_none(root):  # noqa: F811
    assert about._sweep(root) is None and _sweep_line({"sweep": None}) == ""
    sweep_files(root, digest="old")
    assert about._sweep(root) is None                      # 題檔對不上：不用舊數字
    sweep_files(root)
    s = about._sweep(root)
    assert s["hit3"] == {400: 0.75, 600: 0.8, 900: 0.8, 1200: 0.7} and s["n"] == 40
    assert _sweep_line({"sweep": s}) == "掃過 400／600／900／1200 字：Hit@3（三組題合併、40 題單一公司有答案題）依序為 0.750／0.800／0.800／0.700，結論：差異在區間內：測試句"
    (root / "eval/results_chunk_sweep.json").write_text("{壞掉", encoding="utf-8")
    assert about._sweep(root) is None


def test_about_pages_show_the_sentence_only_when_the_file_exists(client, root):  # noqa: F811
    for url in ("/about", "/about?all=1"):
        assert "掃過 400" not in client[1].get(url).get_data(as_text=True)
    sweep_files(root)
    for url in ("/about", "/about?all=1"):
        assert "掃過 400／600／900／1200 字：Hit@3" in client[1].get(url).get_data(as_text=True), url

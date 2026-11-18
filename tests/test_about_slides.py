"""票 37：/about 預設是簡報；每張圖的數字對得上輸出檔（從頁面的 data-v 解析）；缺檔略過、不報 500。Flask test client，假嵌入器，假輸出檔。"""
import json
import re

import pytest

from job_rag import about, retrieval
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import BAD, client  # noqa: F401
from tests.test_cross import _cross_out
from tests.test_threshold_page import E2E
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


def get(client, url="/about"):
    return client[1].get(url)


def slide(html, key):
    m = re.search(rf'<section class="slide" id="p\d+" data-slide="{key}"[^>]*>(.*?)</section>', html, re.S)
    return m.group(1) if m else None


def keys(html):
    return re.findall(r'data-slide="(\w+)"', html)


def vals(sec, attr="data-v"):
    return [float(v) for v in re.findall(rf'{attr}="([-\d.e]+)"', sec)]


def test_default_is_slides_and_all_one_is_the_long_page(client):
    h = get(client).get_data(as_text=True)
    assert keys(h)[:3] == ["cover", "arch", "chunk"] and 'href="/about?all=1"' in h and "<h2>1. " not in h
    long = get(client, "/about?all=1").get_data(as_text=True)
    assert "<h2>1. " in long and "data-slide" not in long


def test_every_slide_has_one_short_claim_and_at_most_two_note_lines(client):
    h = get(client).get_data(as_text=True)
    assert len(keys(h)) >= 8
    for sec in re.findall(r'<section class="slide".*?</section>', h, re.S):
        titles = re.findall(r"<h2>(.*?)</h2>", sec)
        assert len(titles) == 1 and len(titles[0]) <= 18, titles
        sn = re.search(r'<div class="sn">(.*?)</div>', sec, re.S)
        assert not sn or len(re.findall(r"<p", sn.group(1))) <= 2
        assert sec.count("<details class=say>") <= 1 and "<details class=say open" not in sec


def test_dots_match_slides_and_controls_exist(client):
    h = get(client).get_data(as_text=True)
    n = len(keys(h))
    assert len(re.findall(r'<button type="button" aria-label="第 \d+ 頁：', h)) == n
    for i in ("pv", "nx", "pos"):
        assert f'id="{i}"' in h
    assert "ArrowRight" in h and "touchstart" in h and "<script src" not in h and "<img" not in h and "prefers-color-scheme:dark" in h


def test_method_chart_numbers_are_the_output_file_numbers(client, root):  # noqa: F811
    f = json.loads((root / "eval/results_methods.json").read_text(encoding="utf-8"))["methods"]
    sec = slide(get(client).get_data(as_text=True), "methods")
    mrr = re.findall(r'data-m="([\w-]+)" data-v="([\d.e-]+)" data-lo="([\d.e-]+)" data-hi="([\d.e-]+)"', sec)
    assert len(mrr) == 5
    for m, v, lo, hi in mrr:
        assert (float(v), float(lo), float(hi)) == (f[m]["mrr"], f[m]["ci"]["mrr"][0], f[m]["ci"]["mrr"][1])
    hits = re.findall(r'data-m="([\w-]+)" data-k="(hit@\d)" data-v="([\d.e-]+)"', sec)
    assert len(hits) == 15 and all(float(v) == f[m][k] for m, k, v in hits)
    assert [m for m, *_ in mrr] == sorted(f, key=lambda m: -f[m]["mrr"])  # 由高到低


def test_chunk_histogram_counts_sum_to_segment_count(client):
    n = sum(client[0].public_company_counts().values())
    sec = slide(get(client).get_data(as_text=True), "chunk")
    assert sum(vals(sec)) == n and f"{n} 段" in sec


def test_cover_numbers_come_from_data(client, root):  # noqa: F811
    d = about.load(root)
    sec = slide(get(client).get_data(as_text=True), "cover")
    assert len(vals(sec)) == 3 and vals(sec)[-1] == d["n_answerable"] + d["n_unanswerable"]


def test_arch_numbers_follow_constants(client, monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.123)
    monkeypatch.setattr(retrieval, "DEFAULT_K", 9)
    monkeypatch.setattr(retrieval, "CHUNK", 777)
    monkeypatch.setattr(retrieval, "PER_COMPANY", 4)
    monkeypatch.setattr(retrieval, "CROSS_FLOOR", 0.33)
    sec = slide(get(client).get_data(as_text=True), "arch")
    assert "低於 0.123 就停" in sec and "K = 9" in sec and "約 777 字" in sec and "FAISS" in sec and "DeepSeek" in sec
    assert "引用了沒送出的段落編號" in sec and "檢索分兩條路，看在哪裡問" in sec and "在全部公司頁問，沒提公司名" in sec and "取最像的 9 段" in sec and "每家各取 4 段" in sec and "低於 0.33 就停" in sec  # 兩條路徑的數字讀常數
    assert "每家各取 3 段" not in sec and "低於 0.50 就停" not in sec


def test_ragas_slide_numbers_and_the_self_judge_note(client, root):  # noqa: F811
    d = about.load(root)
    sec = slide(get(client).get_data(as_text=True), "ragas")
    a = re.findall(r'data-k="(\w+)" data-v="([\d.e-]+)"', sec)
    assert [(k, float(v)) for k, v in a] == [("faithfulness", d["generation"]["faithfulness"]), ("answer_relevancy", d["generation"]["answer_relevancy"])]
    assert re.search(rf'data-v="{d["cross"]["supported"]}" data-n="{d["cross"]["claims"]}"', sec)
    assert "同模型自評可能偏樂觀" in sec and "K=5" in sec


def test_funnel_uses_end_to_end_file_and_links_to_threshold(client, root):  # noqa: F811
    put(root, "eval/results_endtoend.json", E2E)  # n=2、refused=2、by_gate=1、by_answer_layer=1
    h = get(client).get_data(as_text=True)
    sec = slide(h, "funnel")
    assert re.findall(r'class="fb[ z]*" data-v="(\d+)"', sec) == ["2", "1", "0"]  # 問題 2 → 過門檻 1 → 最後仍回答 0
    assert 'data-v="2" data-n="2"' in sec and "擋下 1 題" in sec and 'href="/threshold"' in sec and "2/2 題拒答" in h


def test_funnel_without_file_says_missing_and_keeps_the_button(client):
    r = get(client)
    sec = slide(r.get_data(as_text=True), "funnel")
    assert r.status_code == 200 and "缺資料" in sec and 'href="/threshold"' in sec and "data-n" not in sec


def test_fixes_cards_skip_what_has_no_source(client, root):  # noqa: F811
    sec = slide(get(client).get_data(as_text=True), "fixes")
    assert sec.count('class="fx"') == 1 and "換找法" in sec and "補上公司名" not in sec  # 假檔沒有 RAGAS 舊輸出與補丁檔
    want = {r["method"]: r["mrr"] for r in about.load(root)["table"]}
    assert vals(sec) == [want["bm25"], want["bge-m3"]]


def test_real_outputs_give_three_fix_cards_and_salary_numbers():
    import pathlib
    top = pathlib.Path(__file__).parent.parent
    if not (top / "eval/results_scoped.txt").exists():
        pytest.skip("沒有 eval 輸出")
    try:
        d = about.load(top)
    except about.AboutDataError:
        pytest.skip("輸出檔不完整")
    from job_rag.about_slides import s_fixes
    sec = s_fixes(d)[1]
    sf = d["salary_fix"]
    assert sf and f"{sf['before']:.2f}" in sec and f"{sf['after']:.2f}" in sec and sec.count('class="fx"') == 3


def test_cross_slide_schematic_always_and_coverage_only_with_fresh_file(client, root):  # noqa: F811
    sec = slide(get(client).get_data(as_text=True), "cross")
    assert f"每家取 {retrieval.PER_COMPANY} 段" in sec and "缺資料" in sec and 'data-k="1"' not in sec
    _cross_out(root)
    sec = slide(get(client).get_data(as_text=True), "cross")
    assert "缺資料" not in sec and re.findall(r'data-k="(\d)" data-v="([\d.]+)"', sec) == [("2", "0.5")]


def test_cross_slide_follows_per_company_constant(client, monkeypatch):
    monkeypatch.setattr(retrieval, "PER_COMPANY", 4)
    assert "每家取 4 段" in slide(get(client).get_data(as_text=True), "cross")


def test_missing_generation_files_drop_the_ragas_slide_without_500(client, root):  # noqa: F811
    (root / "eval/results_generation.json").unlink()
    (root / "eval/crossjudge/judge_gpt.json").unlink()
    r = get(client)
    k = keys(r.get_data(as_text=True))
    assert r.status_code == 200 and "ragas" not in k and "methods" in k


def test_missing_methods_file_shows_one_error_slide_and_no_old_numbers(client, root):  # noqa: F811
    (root / "eval/results_methods.json").unlink()
    r = get(client)
    h = r.get_data(as_text=True)
    assert r.status_code == 500 and "results_methods.json" in slide(h, "error") and "0.875" not in h
    assert {"cover", "arch", "chunk", "limits", "qa"} <= set(keys(h)) and "methods" not in keys(h)


def test_stale_methods_file_is_an_error_slide(client, root):  # noqa: F811
    from tests.test_about_data import QS4
    put(root, "eval/questions.json", {"questions": [dict(QS4[0], question="改過的題目？")] + QS4[1:]})
    r = get(client)
    assert r.status_code == 500 and "題組" in slide(r.get_data(as_text=True), "error")


def test_qa_has_five_one_sentence_answers_with_file_numbers(client):
    sec = slide(get(client).get_data(as_text=True), "qa")
    ans = re.findall(r"<details><summary>[^<]+</summary><p>([^<]+)</p></details>", sec)
    assert len(ans) == 5 and "0.875" in sec and "區間" in sec


def test_slides_never_use_forbidden_wording(client, root):  # noqa: F811
    from scripts.export_public_repo import WORDS
    ok = get(client).get_data(as_text=True)
    (root / "eval/results_methods.json").unlink()
    for text in (ok, get(client).get_data(as_text=True)):
        for w in BAD:
            assert w not in text, w
    src = open("job_rag/about_slides.py", encoding="utf-8").read()
    assert not WORDS.search(src)


def test_hybrid_is_always_written_with_its_two_parts_on_slides(client):
    h = get(client).get_data(as_text=True)
    for key in ("methods", "qa"):
        sec = slide(h, key)
        assert "BM25＋bge-m3" in sec or "（BM25＋bge-m3）" in sec, key


def test_methods_slide_defines_hit_and_mrr_in_plain_words(client, root):  # noqa: F811
    d = about.load(root)
    m3 = next(r for r in d["table"] if r["method"] == "bge-m3")
    sec = slide(get(client).get_data(as_text=True), "methods")
    assert "Hit@3＝正確答案的那段，有排進前 3 名的題數比例" in sec and "Hit@1 是第 1 名、Hit@5 是前 5 名" in sec
    assert f"{d['n_answerable']} 題裡有 {m3['found']} 題前 3 名找到，Hit@3＝{m3['hit@3']:.3f}" in sec and "MRR＝正確段落名次的倒數平均" in sec

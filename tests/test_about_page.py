"""專案說明頁（/about）：Flask test client，假嵌入器，假輸出檔。"""
import re

import pytest

from job_rag import about, retrieval, search
from tests.test_about_data import QS4, put, root  # noqa: F401  (root 是 fixture)
from tests.test_answer import MINI
from tests.test_vector import FakeModel, fake_env  # noqa: F401  (autouse fixture)

BAD = ("AI 協作", "AI協作", "協作", "私人", "你的對應", "作戰卡", "建議你", "你可以", "你要")


@pytest.fixture
def client(monkeypatch, root):  # noqa: F811
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    monkeypatch.setattr(about, "ROOT", root)
    import app as appmod
    return appmod, appmod.app.test_client()


def test_page_has_exactly_six_blocks_in_order(client):
    html = client[1].get("/about").get_data(as_text=True)
    heads = re.findall(r"<h2>(.*?)</h2>", html)
    assert [h.split(" ", 1)[0] for h in heads] == ["1.", "2.", "3.", "4.", "5.", "6."] and len(heads) == 6
    assert len(re.findall(r"<ol class=flow>.*?</ol>", html, re.S)) == 1
    assert len(re.findall(r"<li><b>", html.split("<h2>2.")[1].split("<h2>3.")[0])) == 6  # 流程 6 格
    assert len(re.findall(r"<li><b>", html.split("<h2>3.")[1].split("<h2>4.")[0])) == 5  # 5 個決定


def test_numbers_on_the_page_are_the_output_file_numbers(client):
    html = client[1].get("/about").get_data(as_text=True)
    assert "0.875" in html            # bge-m3 MRR（手算 (1+1+1+0.5)/4）
    assert "0.833" in html            # 忠實度平均 (1+1+0.5)/3
    assert "擋住 1/1" in html and "誤擋 2/4" in html
    assert "已評分 3 題" in html and "5 個陳述中 4 個有依據" in html
    assert "不是 RAGAS" in html
    for name in ("BM25", "bge-small-zh", "multilingual-e5", "bge-m3", "混合"):
        assert name in html


def test_failure_cases_are_shown_and_escaped(client, root):  # noqa: F811
    qs = [dict(QS4[0], question="<b>甲</b>的資本額？")] + QS4[1:]
    # 題組變了，輸出檔會過期；這裡只確認題目文字會被跳脫：用新指紋重寫輸出檔
    from tests.test_about_data import methods_file
    put(root, "eval/questions.json", {"questions": qs})
    put(root, "eval/results_methods.json", methods_file(qs=qs))
    from tests.test_about_data import gen_rows
    put(root, "eval/results_generation.json", gen_rows(qs))
    html = client[1].get("/about").get_data(as_text=True)
    assert "&lt;b&gt;甲&lt;/b&gt;的資本額？" in html and "<b>甲</b>" not in html
    assert "丁用什麼技術？" in html and "0.690" in html  # 被門檻誤擋的案例


@pytest.mark.parametrize("rel", ["eval/results_methods.json", "eval/results_generation.json", "eval/crossjudge/judge_gpt.json"])
def test_missing_output_shows_clear_error_and_no_scores(client, root, rel):  # noqa: F811
    (root / rel).unlink()
    r = client[1].get("/about")
    html = r.get_data(as_text=True)
    assert r.status_code == 500 and "無法顯示" in html and rel.split("/")[-1] in html
    assert "0.875" not in html and "0.833" not in html
    assert len(re.findall(r"<h2>", html)) == 6  # 其餘區塊照常顯示


def test_stale_output_shows_error_not_old_numbers(client, root):  # noqa: F811
    put(root, "eval/questions.json", {"questions": [dict(QS4[0], question="改過的題目？")] + QS4[1:]})
    html = client[1].get("/about").get_data(as_text=True)
    assert "題組" in html and "0.875" not in html


def test_no_forbidden_wording_on_page_or_error_page(client, root):  # noqa: F811
    ok = client[1].get("/about").get_data(as_text=True)
    (root / "eval/results_methods.json").unlink()
    bad = client[1].get("/about").get_data(as_text=True)
    for text in (ok, bad):
        for w in BAD:
            assert w not in text, w


def test_page_has_two_themes_and_no_wide_elements(client):
    html = client[1].get("/about").get_data(as_text=True)
    assert "prefers-color-scheme:dark" in html and "color-scheme:light dark" in html
    assert "width=device-width" in html and "<script" not in html and "<img" not in html


def test_nav_links_both_ways(client):
    c = client[1]
    assert 'href="/about"' in c.get("/").get_data(as_text=True)
    assert 'href="/"' in c.get("/about").get_data(as_text=True)


def test_about_shows_status_page_while_warming_up(client):
    appmod, c = client
    appmod._warm["state"] = "loading"
    try:
        assert "準備中" in c.get("/about").get_data(as_text=True)
    finally:
        appmod._warm["state"] = "ready"


# ---- 頁面上的事實對得上程式 ----
def test_page_says_five_methods_and_the_code_has_five():
    assert len(retrieval.METHODS) == 5


def test_each_passage_is_indexed_with_company_and_heading_prefix():
    search("鯨魚追蹤軟體", method="bge-m3", corpus=MINI)
    texts = [t for name, ts in FakeModel.calls for t in ts]
    assert any(t.startswith("甲科技 1. 基本資料\n") for t in texts)


def test_committed_output_files_match_the_current_question_set():
    d = about.load()  # 真的輸出檔；題組改了卻沒重跑評估，這裡會失敗
    assert d["n_answerable"] == 25 and d["n_unanswerable"] == 5 and len(d["table"]) == 5


def test_page_without_generation_output_says_so_and_keeps_retrieval_scores(client, root):  # noqa: F811
    (root / "eval/results_generation.json").unlink()
    (root / "eval/crossjudge/judge_gpt.json").unlink()
    r = client[1].get("/about")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "0.875" in html and "沒有生成層評估" in html and "RAGAS" in html
    assert "無法顯示" not in html

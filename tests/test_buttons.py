"""問答頁的按鈕：只走 Flask test client 與 search()，假嵌入器。"""
import json
import os
import re
from pathlib import Path

import pytest

from job_rag import public_company_counts, retrieval
from tests.test_answer import FakePost, MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    import app as appmod
    return appmod, appmod.app.test_client()


ROOT = Path(__file__).parent.parent
EVAL = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]
BY_ID = {q["id"]: q for q in EVAL}
LIVE = ["台灣大哥大", "聯合報", "叡揚資訊", "神通資訊", "藍新資訊", "凱基證券", "華電聯網", "奧衍", "中華網龍", "尼諾思", "醫宇宙"]


def body_of(html):
    return html.split("</form>", 1)[1]  # 表單會回顯問題，只看結果區


def test_page_has_the_11_live_company_buttons(client):
    _, c = client
    html = c.get("/").get_data(as_text=True)
    for name in LIVE:
        assert f">{name}</button>" in html, name
    assert len(re.findall(r"name=pick", html)) == 11


def test_company_buttons_match_corpus_company_names():
    # 對照表的值要是語料的公司欄位（尼諾思 -> 尼諾思科技）；環境變數沒指到真語料就跳過
    import app as appmod
    assert [label for label, _ in appmod.LIVE_COMPANIES] == LIVE
    corpus = os.environ.get("JOB_RAG_REAL_CORPUS")
    if not corpus or not Path(corpus).is_dir():
        pytest.skip("沒有真語料（JOB_RAG_REAL_CORPUS）")
    names = public_company_counts(corpus)
    for label, name in appmod.LIVE_COMPANIES:
        assert name in names, (label, name)


def test_selected_company_limits_results_to_that_company(client):
    _, c = client
    body = body_of(c.get("/?q=鯨魚追蹤軟體&company=乙資訊").get_data(as_text=True))
    assert "<b>乙資訊</b>" in body and "<b>甲科技</b>" not in body
    assert "<b>甲科技</b>" in body_of(c.get("/?q=鯨魚追蹤軟體").get_data(as_text=True))


def test_clicking_selected_company_again_clears_it(client):
    _, c = client
    html = c.get("/?q=鯨魚追蹤軟體&company=尼諾思科技").get_data(as_text=True)
    assert re.search(r'name=pick value=""[^>]*>尼諾思</button>', html)  # 已選的那顆再按 = 取消
    assert 'name=pick value="台灣大哥大"' in html


FAQ = {"what": "是做什麼的？", "jobs": "有哪些職缺？", "tech": "的技術堆疊與開發工具有哪些？", "fin": "的營收和近期新聞是什麼？"}


def test_four_faq_buttons_fill_the_selected_company_into_the_question(client):
    _, c = client
    html = c.get("/").get_data(as_text=True)
    for label in ("這家做什麼", "有哪些職缺", "用什麼技術", "財務與新聞"):
        assert f">{label}</button>" in html
    for key, tail in FAQ.items():
        html = c.get(f"/?faq={key}&company=奧衍").get_data(as_text=True)
        assert f'value="奧衍{tail}"' in html, key


def test_faq_without_company_says_so_not_silent(client):
    _, c = client
    body = body_of(c.get("/?faq=what").get_data(as_text=True))
    assert "請先選一家公司" in body and "class='hit" not in body


def test_faq_tails_are_complete_questions_that_fit_any_company():
    import app as appmod
    assert {k: t for k, (_, t) in appmod.FAQ.items()} == FAQ
    for tail in FAQ.values():
        assert tail.endswith("？") and not any(l in tail for l, _ in appmod.LIVE_COMPANIES)  # 通順、不綁特定公司


# ---- Enter（手機鍵盤「前往」）----
def test_first_submit_button_in_form_is_search_so_enter_runs_it(client):
    # 瀏覽器按 Enter 會「按」表單的第一顆提交按鈕；它必須是「查」（沒有 name，不帶 pick／faq／demo／answer）
    _, c = client
    form = re.search(r"<form id=f>(.*?)</form>", c.get("/").get_data(as_text=True), re.S).group(1)
    first = re.search(r"<button(?=[\s>])([^>]*)>(.*?)</button>", form, re.S)
    assert first.group(2) == "查" and "name=" not in first.group(1) and "type=button" not in first.group(1)


# ---- 查無示範 ----
def test_two_demo_buttons_are_unanswerable_eval_questions(client):
    import app as appmod
    assert len(appmod.DEMOS) == 2
    for qid in appmod.DEMOS:
        assert qid.startswith("u") and BY_ID[qid]["answerable"] is False
    _, c = client
    html = c.get("/").get_data(as_text=True)
    for qid in appmod.DEMOS:
        assert f'name=demo value="{qid}"' in html


def test_low_score_shows_notice_dimmed_hits_no_answer_button_no_api(client, monkeypatch):
    appmod, c = client
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 10.0)  # 任何分數都低於門檻
    post = FakePost()
    monkeypatch.setattr(appmod, "_post", post)
    for url in ("/?q=鯨魚追蹤軟體", "/?q=鯨魚追蹤軟體&answer=1", f"/?demo={appmod.DEMOS[0]}"):
        body = body_of(c.get(url).get_data(as_text=True))
        assert "可能沒有答案" in body
        assert "class='hit dim'" in body  # 原文仍顯示，淡色
        assert "整理成答案" not in body
    assert post.calls == []


def test_above_threshold_is_normal(client):
    _, c = client
    body = body_of(c.get("/?q=鯨魚追蹤軟體").get_data(as_text=True))
    assert "可能沒有答案" not in body and "class='hit'" in body and "整理成答案" in body


def test_company_without_any_passage_says_maybe_no_answer(client):
    _, c = client
    body = body_of(c.get("/?q=鯨魚&company=不存在公司").get_data(as_text=True))
    assert "可能沒有答案" in body and "整理成答案" not in body


# ---- 評估成績連結 ----
EVAL_LINK = "看這題在評估裡的成績"


def test_eval_link_only_when_question_equals_an_eval_question(client):
    _, c = client
    same = BY_ID["s01"]["question"]
    html = c.get("/", query_string={"q": same}).get_data(as_text=True)
    assert EVAL_LINK in html and "id=eval" in html
    for near in (same[:-1], same.replace("奧衍", "叡揚資訊"), "鯨魚追蹤軟體"):
        assert EVAL_LINK not in c.get("/", query_string={"q": near}).get_data(as_text=True), near


def test_eval_panel_for_unanswerable_question_says_expected_not_found(client):
    _, c = client
    html = c.get("/", query_string={"q": BY_ID["u07"]["question"]}).get_data(as_text=True)
    assert "不可回答題" in html.split("id=eval", 1)[1]


def test_no_collaboration_wording(client):
    _, c = client
    text = c.get("/").get_data(as_text=True) + (ROOT / "README.md").read_text(encoding="utf-8")
    for bad in ("AI 協作", "AI協作", "協作"):
        assert bad not in text

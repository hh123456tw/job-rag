"""專案說明頁（/about）：Flask test client，假嵌入器，假輸出檔。"""
import os
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
    assert len(re.findall(r"<li><b>", html.split("<h2>1.")[1].split("<h2>2.")[0])) == 6  # 流程 6 格（第 1 段）
    # 原本的 5 個設計決定，依主題分在第 2、3、4 段（共 5 個，一個都沒少）
    want = {2: ["依標題切段，每段前面加公司名。", "只用公開事實。"], 3: ["比較五種找法。"],
            4: ["答案優先，失敗時回到原文。", "沒把握就說「可能沒有答案」。"]}
    for n, titles in want.items():
        sec = html.split(f"<h2>{n}.")[1].split(f"<h2>{n + 1}.")[0]
        assert [t for t in re.findall(r"<li><b>([^<]+)</b>", sec) if t in titles] == titles


def test_every_block_has_claim_evidence_and_script_in_the_walkthrough_order(client):
    html = client[1].get("/about").get_data(as_text=True)
    order = re.search(r"<div class=order><b>講解順序</b><ol>(.*?)</ol>", html, re.S).group(1)
    assert re.findall(r"href=#(\w+)", order) == ["s1", "s2", "s3", "s4", "s5", "s6", "qa"]
    titles = [h.split(" ", 1)[1].rsplit(" <span", 1)[0] for h in re.findall(r"<h2>(.*?)</h2>", html)]
    assert titles == ["這是什麼", "資料與切段", "怎麼找", "怎麼確認答對", "踩到的坑與三次修正", "限制與下一步"]
    for n in range(1, 7):
        sec = re.search(rf"<section id=s{n} class=seg>(.*?)</section>", html, re.S).group(1)
        assert "約 30 秒" in sec and sec.count("<p class=claim>") == 1  # 步驟編號、時間、一句話主張
        assert len(re.findall(r"<details class=say><summary>講稿：這樣說</summary>", sec)) == 1 and "<details class=say open" not in sec
        say = re.search(r"<details class=say>(.*?)</details>", sec, re.S).group(1)
        assert 3 <= len(re.findall(r"<li>", say)) <= 8  # 短：每段 3 到 8 句


def test_qa_section_has_five_questions_and_stays_out_of_the_six_numbered_blocks(client):
    html = client[1].get("/about").get_data(as_text=True)
    qa = re.search(r"<section id=qa class=seg>(.*?)</section>", html, re.S).group(1)
    qs = re.findall(r"<summary>([^<]+)</summary>", qa)
    assert len(qs) == 5 and any("100 倍" in q for q in qs) and any("reranker" in q for q in qs) and any("混合" in q for q in qs)
    assert any("太樂觀" in q for q in qs) and any("向量資料庫" in q for q in qs)
    assert "區間含 0" in qa and "0.875" in qa  # 數字取自輸出檔


def test_presentation_mode_controls_and_keys_exist(client):
    html = client[1].get("/about").get_data(as_text=True)
    assert "id=pmbtn type=button hidden>簡報模式" in html  # 沒有 JS 時不顯示
    for i in ("pmprev", "pmnext", "pmx"):
        assert f"id={i}" in html
    assert "ArrowRight" in html and "ArrowLeft" in html and html.count("<script") == 1 and "<script src" not in html


def test_scripts_skip_number_sentences_when_output_is_missing(client, root):  # noqa: F811
    (root / "eval/results_methods.json").unlink()
    html = client[1].get("/about").get_data(as_text=True)
    say = "".join(re.findall(r"<details class=say>(.*?)</details>", html, re.S))
    assert "0.875" not in html and "道有答案的題目" not in say and "MRR 的意思" not in say
    assert len(re.findall(r"<details class=say>", html)) == 6


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
    assert len(re.findall(r"<h2>", html)) == 6 and "<h2 class=qa>" in html  # 其餘區塊照常顯示


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
    assert "width=device-width" in html and "<script src" not in html and "<img" not in html  # 只有簡報模式的一段內嵌 JS


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


@pytest.mark.skipif(not os.environ.get("JOB_RAG_REAL_QUESTIONS"), reason="需要私人 repo 的完整題組與評估輸出（JOB_RAG_REAL_QUESTIONS）")
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


# ---- 票 21：白話改版與「答案優先」的事實 ----
def test_three_stat_cards_match_the_output_files(client):
    html = client[1].get("/about").get_data(as_text=True)
    cards = re.findall(r"<div class=stat><b>([^<]+)</b><span>([^<]+)</span>", html)
    assert [c[0] for c in cards] == ["4 / 4", "1 / 1", "4 / 5"]  # bge-m3 前 3 名 4/4；不可回答題擋住 1/1；GPT 複查 5 個陳述 4 個有依據
    assert "前 3 名" in cards[0][1] and "可能沒有答案" in cards[1][1] and "5 個說法" in cards[2][1]


def test_bars_are_sorted_by_found_count_and_numbers_match(client):
    html = client[1].get("/about").get_data(as_text=True)
    bars = re.findall(r"<span class=lab>([^<]+)<small>([^<]+)</small>( <em>最好</em>)?</span><span class=track><i style='width:([\d.]+)%'></i></span><b>(\d+) / 4</b>", html)
    assert [(b[0], int(b[4])) for b in bars] == [("大型向量模型", 4), ("關鍵字加向量", 4), ("小型向量模型", 3), ("關鍵字比對", 2), ("另一個向量模型", 2)]
    assert [float(b[3]) for b in bars] == [100.0, 100.0, 75.0, 50.0, 50.0]
    assert [bool(b[2]) for b in bars] == [True, True, False, False, False]  # 並列最多的都標「最好」
    assert [b[1] for b in bars][:3] == ["bge-m3", "混合", "bge-small-zh"]  # 內部名稱放小字


def test_detailed_numbers_are_in_a_collapsed_details_with_plain_mrr(client):
    html = client[1].get("/about").get_data(as_text=True)
    d = re.search(r"<details class=more><summary>看詳細數字</summary>(.*?)</details>", html, re.S)
    assert d and "<details class=more open" not in html  # 預設收合
    assert "正確段落平均排第幾名的倒數，越接近 1 越好" in d.group(1) and "0.875" in d.group(1) and "95% 信賴區間" in d.group(1)


def test_about_describes_answer_first_and_not_the_old_behavior(client):
    html = client[1].get("/about").get_data(as_text=True)
    assert "答案優先，失敗時回到原文" in html and "點一家公司，直接問問題" in html
    for old in ("預設只顯示原文", "按鈕才用 LLM", "按鈕才呼叫 LLM", "整理成答案"):
        assert old not in html, old
    # 對得上程式：答案的來源是 /api/answer，失敗與低分的行為由 tests/test_chat.py、tests/test_answer_first.py 驗證
    import app as appmod
    assert any(r.rule == "/api/answer" for r in appmod.app.url_map.iter_rules())


def test_stat_cards_hide_when_output_is_missing_and_error_stays(client, root):  # noqa: F811
    (root / "eval/results_methods.json").unlink()
    html = client[1].get("/about").get_data(as_text=True)
    assert "class=stat>" not in html and "無法顯示" in html and "class=bars" not in html
    assert "0.875" not in html


def test_without_generation_output_third_card_says_none(client, root):  # noqa: F811
    (root / "eval/results_generation.json").unlink()
    (root / "eval/crossjudge/judge_gpt.json").unlink()
    html = client[1].get("/about").get_data(as_text=True)
    cards = re.findall(r"<div class=stat><b>([^<]+)</b>", html)
    assert cards == ["4 / 4", "1 / 1", "沒有"]


def test_mrr_and_ragas_are_explained_as_lists_outside_the_details(client):
    html = client[1].get("/about").get_data(as_text=True)
    outside = re.sub(r"<details class=more>.*?</details>", "", html, flags=re.S)
    assert "<h3>MRR（平均倒數名次）</h3><ul class=plain>" in outside and "1 ÷ 名次" in outside and "0.875" in outside  # bge-m3 的 MRR 取自輸出檔
    assert "<h3>RAGAS</h3><ul class=plain>" in outside and "忠實度 " in outside and "答案相關性 " in outside
    assert "偏愛自己的答案" in outside and "GPT 複查" in outside


def test_rag_level_list_has_done_and_not_done_and_numbers_match_the_outputs(client):
    html = client[1].get("/about").get_data(as_text=True)
    lv = re.search(r"<div class=level>(.*?)</ul></div></div>", html, re.S).group(1)
    assert "<h3>做了</h3>" in lv and "<h3>刻意沒做</h3>" in lv
    assert "MRR 0.875" in lv and "RAGAS 忠實度" in lv and "5 個說法中 4 個有依據" in lv  # 數字取自輸出檔
    assert f"最高相似度低於 {retrieval.NOT_FOUND_THRESHOLD:.3f}" in lv  # 門檻取自程式常數
    for w in ("重排序模型", "向量資料庫", "微調模型", "線上監控", "獨立測試題"):
        assert w in lv
    assert re.search(r"<section id=s6 class=seg><h2>6\. 限制與下一步.*?class=level.*?</section>", html, re.S)  # 放在第 6 段，仍只有 6 塊


def test_without_generation_output_ragas_says_so_but_mrr_stays(client, root):  # noqa: F811
    (root / "eval/results_generation.json").unlink()
    (root / "eval/crossjudge/judge_gpt.json").unlink()
    outside = re.sub(r"<details class=more>.*?</details>", "", client[1].get("/about").get_data(as_text=True), flags=re.S)
    assert "<h3>MRR（平均倒數名次）</h3>" in outside and "沒有生成層評估" in outside

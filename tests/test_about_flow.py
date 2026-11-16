"""票 22 追加：/about 流程每一格下面一句「我們怎麼做」。數字與參數來自程式常數與載入結果，不手寫。"""
import re

import pytest

from job_rag import METHODS, memory, retrieval, search
from tests.test_about_data import root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import BAD, client  # noqa: F401
from tests.test_answer import MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


def cells(html):
    flow = re.search(r"<ol class=flow>(.*?)</ol>", html, re.S).group(1)
    return [(b, re.sub(r"<[^>]+>", "", s)) for b, s in re.findall(r"<li><b>(.*?)</b><small>(.*?)</small></li>", flow, re.S)]


def test_six_cells_each_with_exactly_one_short_sentence_below_the_title(client):
    c = cells(client[1].get("/about?all=1").get_data(as_text=True))
    assert len(c) == 6
    for title, s in c:
        assert 0 < len(s) <= 60 and s.count("。") == 1 and s.endswith("。"), (title, s)


def test_numbers_come_from_constants_and_loaded_corpus(client):
    appmod, cl = client
    s = [t for _, t in cells(cl.get("/about?all=1").get_data(as_text=True))]
    counts = appmod.public_company_counts()
    n_co = len([c for c in counts if c != "綜合"])
    assert s[0].startswith(f"{n_co} 家調查筆記") and f"共 {sum(counts.values())} 段" in s[0]
    assert f"約 {retrieval.CHUNK} 字、重疊 {retrieval.OVERLAP} 字" in s[1]
    assert f"用 {retrieval.DEFAULT_METHOD}" in s[2] and f"前 {retrieval.DEFAULT_K} 段" in s[2] and f"比較了 {len(METHODS)} 種找法" in s[2]
    assert "立刻顯示" in s[3] and "公司、檔名與標題" in s[3]
    assert "DeepSeek" in s[4] and "出處編號" in s[4] and f"最近 {memory.MAX_TURNS} 輪對話" in s[4]
    assert f"低於 {retrieval.NOT_FOUND_THRESHOLD:.3f}" in s[5] and "不呼叫 DeepSeek" in s[5] and "回到原文" in s[5]


def test_changing_constants_changes_the_page(client, monkeypatch):
    monkeypatch.setattr(retrieval, "NOT_FOUND_THRESHOLD", 0.123)
    monkeypatch.setattr(retrieval, "CHUNK", 777)
    monkeypatch.setattr(retrieval, "OVERLAP", 11)
    monkeypatch.setattr(retrieval, "DEFAULT_K", 9)
    monkeypatch.setattr(memory, "MAX_TURNS", 5)
    s = [t for _, t in cells(client[1].get("/about?all=1").get_data(as_text=True))]
    assert "低於 0.123" in s[5] and "約 777 字、重疊 11 字" in s[1] and "前 9 段" in s[2] and "最近 5 輪" in s[4]


def test_default_k_is_what_search_really_uses():
    assert search.__defaults__ is not None and retrieval.DEFAULT_K in search.__defaults__ and retrieval.DEFAULT_METHOD in search.__defaults__


def test_no_forbidden_wording_and_missing_eval_files_do_not_change_the_flow(client, root):  # noqa: F811
    html = client[1].get("/about?all=1").get_data(as_text=True)
    assert not any(w in html for w in BAD)
    (root / "eval/results_generation.json").unlink()
    (root / "eval/crossjudge/judge_gpt.json").unlink()
    assert cells(client[1].get("/about?all=1").get_data(as_text=True)) == cells(html)

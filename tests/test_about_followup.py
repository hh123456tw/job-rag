"""票 22：/about 的對話記憶小段。數字來自 eval/results_followups.json；缺檔時頁面不變。"""
import json
import re

import pytest

from job_rag import about, followups
from tests.test_about_data import put, root  # noqa: F401  (root 是 fixture)
from tests.test_about_page import BAD, client  # noqa: F401
from tests.test_answer import MINI  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)

FQ = [{"id": f"f{i}", "company": "", "previous": "p", "question": "那薪水呢？", "gold": []} for i in range(1, 4)]


def result(plain=1, expand=3, n=3, dg=None):
    return {"digest": dg or followups.digest(FQ), "n": n, "expanded_ids": ["f1", "f2"],
            "no_expand": {"found": plain, "hit@3": plain / n, "ranks": {}}, "expand": {"found": expand, "hit@3": expand / n, "ranks": {}}}


def with_followups(root, res=None):  # noqa: F811
    put(root, "eval/followups.json", {"questions": FQ})
    put(root, "eval/results_followups.json", res or result())


def section3(html):  # 對話記憶那一小段現在在第 6 段（限制與下一步）
    return html.split("<h2>6.")[1].split("<h2 class=qa>")[0]


def test_paragraph_shows_numbers_from_the_output_file_and_the_limit(client, root):  # noqa: F811
    with_followups(root)
    html = client[1].get("/about").get_data(as_text=True)
    t = re.sub(r"<[^>]+>", "", section3(html))
    assert "最近 2 輪" in t and "只用 3 題量過" in t and "不補全 1/3" in t and "補全 3/3" in t
    assert "只量了檢索，沒有量多輪答案品質" in t
    assert not any(w in html for w in BAD)


def test_numbers_follow_the_file_even_when_completion_did_not_help(client, root):  # noqa: F811
    with_followups(root, result(plain=2, expand=2))
    t = re.sub(r"<[^>]+>", "", section3(client[1].get("/about").get_data(as_text=True)))
    assert "不補全 2/3" in t and "補全 2/3" in t


def test_missing_file_leaves_the_page_exactly_as_before(client, root):  # noqa: F811
    html = client[1].get("/about").get_data(as_text=True)
    assert "記在瀏覽器" not in html and "沒有量多輪答案品質" not in html and client[1].get("/about").status_code == 200


def test_stale_file_shows_an_error_line_only_in_that_paragraph(client, root):  # noqa: F811
    with_followups(root, result(dg="0" * 64))
    r = client[1].get("/about")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "對不上" in section3(html) and "不補全" not in section3(html)
    assert "0.875" in html  # 其他區塊的數字照常


def test_broken_file_is_an_error_line_too(client, root):  # noqa: F811
    put(root, "eval/followups.json", {"questions": FQ})
    put(root, "eval/results_followups.json", "{壞的")
    html = client[1].get("/about").get_data(as_text=True)
    assert "results_followups.json" in section3(html)

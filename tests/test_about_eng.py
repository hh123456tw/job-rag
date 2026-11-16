"""票 29、30：/about 第 4 塊底下的「給工程面試官」收合區，與找法成績旁的「三次修正」。Flask test client，假嵌入器，假輸出檔。"""
import inspect
import re

import pytest

from job_rag import about, answer, retrieval
from tests.test_about_data import QS4, put, root  # noqa: F401  (root 是 fixture)
from tests.test_answer import MINI
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


@pytest.fixture
def client(monkeypatch, root):  # noqa: F811
    monkeypatch.setenv("JOB_RAG_CORPUS", str(MINI))
    monkeypatch.setattr(about, "ROOT", root)
    import app as appmod
    return appmod.app.test_client()


def eng(client) -> str:
    html = client.get("/about").get_data(as_text=True)
    m = re.search(r"<details class=eng><summary>給工程面試官：技術細節</summary>(.*?)</details>", html, re.S)
    assert m, "找不到收合區"
    return m.group(1)


def test_eng_details_is_collapsed_and_sits_inside_block_four(client):
    html = client.get("/about").get_data(as_text=True)
    assert len(re.findall(r"<h2>", html)) == 6  # 仍只有 6 個編號區塊
    block4 = html.split("<h2>4.")[1].split("<h2>5.")[0]
    assert "<details class=eng><summary>給工程面試官：技術細節</summary>" in block4
    assert "<details class=eng open" not in html  # 預設收合


def test_architecture_diagram_boxes_match_the_code(client):
    arch = re.search(r"<div class=arch>(.*?)</div>", eng(client), re.S)
    assert arch
    text = arch.group(1)
    main = re.findall(r"<li class=box><b>([^<]+)</b>", re.search(r"<ol class=pipe>(.*?)</ol>", text, re.S).group(1))
    assert main == ["公開資料", "切段", "向量", "索引", "取前 K 段", "查無門檻", "生成", "答案與出處"]
    assert f"{retrieval.DEFAULT_METHOD}，本機" in text  # 向量模型取自常數，本機載入
    assert "FAISS" in text and "IndexFlatIP" in inspect.getsource(retrieval._index)  # 圖上說 FAISS，程式真的用
    assert f"前 {retrieval.DEFAULT_K} 段" in text
    assert f"{retrieval.NOT_FOUND_THRESHOLD:.3f}" in text
    assert "deepseek" in answer.DEFAULT_MODEL and "DeepSeek" in text
    assert "評估迴路" in text and "MRR" in text and "RAGAS" in text and "另一個 AI 複查" in text
    assert "模式隔離" in text and "展示" in text and "自用" in text and retrieval.MODES == ("demo", "self")


def test_no_eng_details_when_output_is_missing(client, root):  # noqa: F811
    (root / "eval/results_methods.json").unlink()
    html = client.get("/about").get_data(as_text=True)
    assert "給工程面試官" not in html and len(re.findall(r"<h2>", html)) == 6


# ---- 切段長度分佈 ----
def test_histogram_bins_cover_every_length_and_sum_to_segment_count():
    from job_rag.about_page import hist
    lens = [1, 100, 101, 250, 599, 600, 601, 900]  # 超過切塊上限的也要有地方放（最後一格開放）
    bins = hist(lens)
    assert [n for _, n in bins] == [2, 1, 1, 0, 0, 4] and sum(n for _, n in bins) == len(lens)
    assert [lab for lab, _ in bins][0] == "1–100" and [lab for lab, _ in bins][-1] == "501 以上"
    assert sum(n for _, n in hist([])) == 0


def test_length_section_numbers_come_from_the_loaded_segments(client):
    import statistics
    text = eng(client)
    lens = retrieval.public_segment_lengths()
    assert lens and len(lens) == sum(retrieval.public_company_counts().values())
    sec = re.search(r"<h3>切段長度</h3>(.*?)(?=<h3>|$)", text, re.S).group(1)
    rows = re.findall(r"<li><span class=lab>([^<]+)</span><span class=track><i style='width:[\d.]+%'></i></span><b>(\d+)</b></li>", sec)
    assert len(rows) == 6 and sum(int(n) for _, n in rows) == len(lens)  # 區間總和等於段數
    assert f"共 {len(lens)} 段" in sec and f"平均 {statistics.mean(lens):.0f} 字" in sec
    assert f"中位數 {statistics.median(lens):.0f} 字" in sec and f"最長 {max(lens)} 字" in sec
    assert f"約 {retrieval.CHUNK} 字、重疊 {retrieval.OVERLAP} 字" in sec and "先依標題切" in sec

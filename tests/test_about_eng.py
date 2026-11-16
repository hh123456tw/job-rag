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
    html = client.get("/about?all=1").get_data(as_text=True)
    m = re.search(r"<details class=eng><summary>給工程面試官：技術細節</summary>(.*?)</details>", html, re.S)
    assert m, "找不到收合區"
    return m.group(1)


def test_eng_details_is_collapsed_and_sits_inside_block_six(client):
    html = client.get("/about?all=1").get_data(as_text=True)
    assert len(re.findall(r"<h2>", html)) == 6  # 仍只有 6 個編號區塊
    block6 = html.split("<h2>6.")[1].split("<h2 class=qa>")[0]
    assert "<details class=eng><summary>給工程面試官：技術細節</summary>" in block6
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
    html = client.get("/about?all=1").get_data(as_text=True)
    assert "給工程面試官" not in html and len(re.findall(r"<h2>", html)) == 6


# ---- 切段長度分佈 ----
def test_histogram_bins_cover_every_length_and_sum_to_segment_count():
    from job_rag.about_page import hist
    lens = [1, 100, 101, 250, 599, 600, 601, 900]  # 超過切塊上限的也要有地方放（最後一格開放）
    bins = hist(lens)
    assert [n for _, n in bins] == [2, 1, 1, 0, 0, 4] and sum(n for _, n in bins) == len(lens)
    assert [lab for lab, _ in bins][0] == "1–100 字" and [lab for lab, _ in bins][-1] == "501 字以上"
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


# ---- 取捨、放大 100 倍、限制 ----
SPACES = """| 項目 | 核心 0、1（較快） | 核心 16、17（較慢） |
|---|---|---|
| 載入 bge-m3 | 9.3 秒 | 18.6 秒 |
| 預熱後單次查詢，bge-m3，中位數（20 次） | 0.14 秒 | 0.28 秒 |
"""


def trade_rows(client) -> dict:
    sec = re.search(r"<h3>為什麼選這個，不選那個</h3><ul class=trade>(.*?)</ul>", eng(client), re.S).group(1)
    return dict(re.findall(r"<li><b>([^<]+)</b><span>([^<]+)</span></li>", sec))


def test_tradeoff_rows_exist_and_numbers_come_from_the_output_files(client):
    rows = trade_rows(client)
    assert list(rows) == ["選 FAISS，不選 Qdrant／Milvus", "選 bge-m3，不選 bge-small-zh／multilingual-e5", "不加重排序模型（reranker）",
                          "不用混合檢索", "DeepSeek 生成與評審，另請 GPT 複查"]
    n = sum(retrieval.public_company_counts().values())
    assert f"只有 {n} 段" in rows["選 FAISS，不選 Qdrant／Milvus"]
    m3 = rows["選 bge-m3，不選 bge-small-zh／multilingual-e5"]
    assert "0.875" in m3 and "0.833" not in m3  # 夾具：bge-m3 MRR 手算 0.875
    assert "沒量過載入與編碼時間" in m3  # 沒有紀錄的數字不寫
    rr = rows["不加重排序模型（reranker）"]
    assert "沒量過" in rr and "0.875" in rr and "有量" not in rr and "證明" not in rr
    hy = rows["不用混合檢索"]
    assert re.search(r"MRR 差 [+-]0\.\d{3}，95% 區間 \[[+-]0\.\d{3}, [+-]0\.\d{3}\]", hy) and "數據沒有支持" in hy
    assert "自我偏好" in rows["DeepSeek 生成與評審，另請 GPT 複查"] or "偏愛自己" in rows["DeepSeek 生成與評審，另請 GPT 複查"]


def test_performance_numbers_only_when_the_record_file_exists(client, root):  # noqa: F811
    assert "9.3" not in trade_rows(client)["選 bge-m3，不選 bge-small-zh／multilingual-e5"]  # 沒有紀錄檔就不寫
    put(root, "eval/spaces_feasibility.md", SPACES)
    m3 = trade_rows(client)["選 bge-m3，不選 bge-small-zh／multilingual-e5"]
    assert "載入約 9.3 秒" in m3 and "中位數約 0.14 秒" in m3 and "不是雲端實測" in m3 and "eval/spaces_feasibility.md" in m3
    put(root, "eval/spaces_feasibility.md", "沒有表格")  # 對不上格式也不寫，不猜
    assert "9.3" not in trade_rows(client)["選 bge-m3，不選 bge-small-zh／multilingual-e5"]


def test_hybrid_difference_matches_the_committed_output_text():
    d = about.load()  # 真的輸出檔（repo 內已有）
    txt = (about.ROOT / "eval/results_methods.txt").read_text(encoding="utf-8")
    want = re.search(r"bge-m3 減 hybrid 的 MRR 差：([+-]\d\.\d{3})，95% 區間 \[([+-]\d\.\d{3}), ([+-]\d\.\d{3})\]", txt).groups()
    got = d["mrr_diff"]
    assert (f"{got['diff']:+.3f}", f"{got['lo']:+.3f}", f"{got['hi']:+.3f}") == want


def test_scale_up_is_labeled_design_note_and_lists_six_items(client):
    sec = re.search(r"<h3>資料放大 100 倍會怎麼改</h3>(.*?)(?=<h3>|$)", eng(client), re.S).group(1)
    assert "設計說明，不是已實作" in sec
    assert len(re.findall(r"<li>", sec)) == 6
    for w in ("HNSW", "增量索引", "PDF", "OCR", "快取", "權限", "多使用者", "評估集", "觀測"):
        assert w in sec


def test_not_done_claims_are_really_absent_in_the_code():
    import pathlib
    src = "\n".join(p.read_text(encoding="utf-8") for p in pathlib.Path("job_rag").glob("*.py") if p.name != "about_page.py")
    src += pathlib.Path("app.py").read_text(encoding="utf-8")
    for w in ("CrossEncoder", "qdrant", "milvus", "hnsw", "langfuse", "langsmith", "opentelemetry", "pdfplumber", "pytesseract"):
        assert w.lower() not in src.lower(), w


def test_limits_section_has_four_lines(client):
    sec = re.search(r"<h3>目前限制</h3>(.*?)(?=<h3>|$)", eng(client), re.S).group(1)
    items = re.findall(r"<li>([^<]+)</li>", sec)
    assert len(items) == 4 and "單機" in items[0] and "存取碼" in items[1] and "本人密碼" in items[1]
    assert "4 題" in items[2] and "獨立測試題" in items[3]


# ---- 票 30：三次用數據做的修正 ----
RUN1 = "eval/results_generation_run1_judge_without_company.json"


def run1_rows():
    from tests.test_about_data import gen_rows
    rows = gen_rows()
    for r, f in zip((r for r in rows if r["status"] == "已評分"), (0.5, 1.0, 0.0)):
        r["faithfulness"] = f  # 平均 0.5
    return rows


def fixes(client) -> list[str]:
    html = client.get("/about?all=1").get_data(as_text=True)
    m = re.search(r"<h3>三次用數據做的修正</h3><ul class=plain>(.*?)</ul>", html, re.S)
    assert m, "找不到修正段"
    assert m.start() < html.index("<details class=eng>")  # 在找法成績旁，不在收合區裡
    return re.findall(r"<li>(.*?)</li>", m.group(1), re.S)


@pytest.fixture
def full(root):  # noqa: F811
    put(root, RUN1, run1_rows())
    put(root, "eval/live_test.md", "# 真實連線測試\n")
    return root


def test_three_fixes_show_numbers_from_the_files(client, full):
    items = fixes(client)
    assert len(items) == 4
    assert "BM25" in items[0] and "bge-m3" in items[0]
    assert "0.550" in items[0] and "0.875" in items[0] and "→" in items[0]  # 夾具手算：BM25 (0+0.2+1+1)/4，bge-m3 (1+1+1+0.5)/4
    assert "數據沒有支持" in items[1] and "原本預期混合會贏" in items[1] and re.search(r"[+-]0\.\d{3}，95% 區間 \[", items[1])
    assert "第一次" in items[2] and "舊題組" in items[2] and "評審沒看到公司名" in items[2]
    assert "0.500" in items[2] and "0.833" in items[2] and "評分 3 題" in items[2]  # 第一次 → 修正後
    assert "不再把" in items[3] and "已採用" in items[3] and "仍抓到其他類型的錯誤" in items[3] and "eval/live_test.md" in items[3]


@pytest.mark.parametrize("rel,gone", [(RUN1, "第一次"), ("eval/live_test.md", "提示詞修正")])
def test_missing_file_skips_only_that_item(client, full, rel, gone):
    (full / rel).unlink()
    items = fixes(client)
    assert len(items) == 3 and not any(gone in i for i in items)
    assert any("BM25" in i for i in items) and any("混合" in i for i in items)


def test_broken_run1_file_skips_the_item_not_the_page(client, full):
    put(full, RUN1, "{不是 json")
    r = client.get("/about?all=1")
    assert r.status_code == 200 and not any("第一次" in i for i in fixes(client))


def test_no_generation_output_skips_the_ragas_fix(client, full):
    (full / "eval/results_generation.json").unlink()
    (full / "eval/crossjudge/judge_gpt.json").unlink()
    assert not any("第一次" in i for i in fixes(client))


def test_fixes_have_no_forbidden_wording(client, full):
    html = client.get("/about?all=1").get_data(as_text=True)
    for w in ("AI 協作", "AI協作", "協作", "私人"):
        assert w not in html

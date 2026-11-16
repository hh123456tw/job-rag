"""載入語料時丟掉含「面試」的行。只丟內文行；標題行不丟（丟了會讓排除段落的內容併進上一段）。"""
from pathlib import Path

from job_rag import interview_drops, search

MINI = Path(__file__).parent / "fixtures" / "mini"


def q(text, **kw):
    return search(text, corpus=MINI, method="bm25", **kw)


def test_line_with_interview_word_is_not_searchable():
    assert q("麋鹿面試") == []
    assert q("麋鹿") == []


def test_other_lines_of_the_same_segment_stay():
    texts = " ".join(h["text"] for h in q("後端工程師 FastAPI 月薪", k=10))
    assert "徵後端工程師" in texts
    assert "面試" not in texts


def test_near_miss_words_are_not_dropped():
    # 面談、筆試、口試都不含「面試」二字：保留
    hit = q("駱駝面談")
    assert hit and "面談地點在高雄" in hit[0]["text"]


def test_interview_heading_does_not_leak_its_body_into_public_text():
    # 「## 6. 面試流程」是標題行，不能被丟掉；它的內容仍屬排除段落
    assert q("珊瑚礁") == []


def test_drop_report_separates_public_from_excluded_segments():
    drops = interview_drops(MINI)
    public = [d for d in drops if d["public"]]
    assert [d["line"] for d in public] == ["職缺說明：面試官由部門主管擔任，月休八天。獨特詞彙：麋鹿面試。"]
    assert public[0]["file"] == "01_甲科技.md" and public[0]["heading_path"].endswith("職缺（後端）")
    assert any(not d["public"] for d in drops)  # 排除段落裡的面試行也有記錄，但不算誤丟


# --- 表格列：只移除含「面試」的欄位，保留其他欄位 ---
TABLE = """# 01 丙公司 廠商深查

## 4. 職缺
| 職缺 | 網址 | 備註 |
|---|---|---|
| 數據分析師 | https://www.104.com.tw/job/aaa | 面試：45 分鐘 SQL 筆試 |
| 資料工程師 | https://www.104.com.tw/job/bbb | 持有證書者優先面試 |
| 後端工程師 | https://www.104.com.tw/job/ccc | 面試官由主管擔任 |
| 前端工程師 | https://www.104.com.tw/job/ddd | 月薪四萬 |
| 面試：只有這欄 | 面試官：王 |  |

## 5. 技術堆疊
Python。

## 2. 業務與財務
做軟體。

## 1. 基本資料
總部在台北。
"""


def table_text(tmp_path):
    (tmp_path / "01_丙公司.md").write_text(TABLE, encoding="utf-8")
    return " ".join(h["text"] for h in search("數據分析師 資料工程師 後端工程師 前端工程師 只有這欄", corpus=tmp_path, method="bm25", k=10))


def test_table_row_keeps_title_and_url_and_drops_only_interview_cell(tmp_path):
    t = table_text(tmp_path)
    for kept in ("數據分析師", "job/aaa", "資料工程師", "job/bbb", "後端工程師", "job/ccc"):
        assert kept in t
    for gone in ("面試", "45 分鐘", "優先", "王"):
        assert gone not in t


def test_table_row_without_interview_word_is_unchanged(tmp_path):
    assert "| 前端工程師 | https://www.104.com.tw/job/ddd | 月薪四萬 |" in table_text(tmp_path)


def test_table_row_with_only_interview_cells_is_removed(tmp_path):
    assert "只有這欄" not in table_text(tmp_path)


def test_table_drop_report_lists_original_row(tmp_path):
    (tmp_path / "01_丙公司.md").write_text(TABLE, encoding="utf-8")
    lines = [d["line"] for d in interview_drops(tmp_path) if d["public"]]
    assert "| 數據分析師 | https://www.104.com.tw/job/aaa | 面試：45 分鐘 SQL 筆試 |" in lines
    assert len(lines) == 4


def test_table_row_from_third_party_interview_site_is_dropped_whole(tmp_path):
    (tmp_path / "01_丙公司.md").write_text(TABLE.replace(
        "| 面試：只有這欄 | 面試官：王 |  |",
        "| 面試趣有資訊類心得 | 軟體工程師 | https://interview.tw/c/zzz | 第三方 |"), encoding="utf-8")
    t = " ".join(h["text"] for h in search("軟體工程師 數據分析師", corpus=tmp_path, method="bm25", k=10))
    assert "interview.tw" not in t and "第三方" not in t

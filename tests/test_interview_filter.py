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

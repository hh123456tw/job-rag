"""票 22：提示詞組裝結果。真的模型行為要用真 DeepSeek 另外驗；這裡只驗送出的內容有哪些規則與區塊。"""
import json

from job_rag import search
from job_rag.answer import SYSTEM, answer
from tests.test_answer import MINI, PUB, FakePost, sent_text  # noqa: F401
from tests.test_answer import key  # noqa: F401  (autouse fixture)

# 真實測試的尼諾思案例（eval/crossjudge/live_input.json L14）：段落只說這個「頁面」存在，沒說公司採用
NINO = {"company": "尼諾思科技", "file": "05_尼諾思.md", "heading_path": "5. 技術堆疊",
        "text": "- 【自述】ROS 2、MoveIt、Gazebo。\n- 【自述】AMD Vitis AI／FPGA／DPU 的頁面。\n- 語言、雲端、框架：查無。"}
HIST = [{"q": "甲科技有哪些職缺？", "a": "徵後端工程師 [1]"}, {"q": "那薪水呢？", "a": "月薪四萬到六萬 [1]"}]


def system_of(post):
    return post.calls[0][2]["messages"][0]["content"]


def user_of(post):
    return post.calls[0][2]["messages"][1]["content"]


def test_history_block_is_in_the_user_message_with_the_evidence_warning():
    post = FakePost()
    answer("那需要作品集嗎？", [PUB], post=post, history=HIST)
    u = user_of(post)
    assert "先前對話" in u and "問：甲科技有哪些職缺？" in u and "答：月薪四萬到六萬 [1]" in u
    assert u.index("先前對話") < u.index("段落：") < u.index("問題：那需要作品集嗎？")  # 順序：先前對話、段落、當前問題
    s = system_of(post)
    assert "只用來理解「那」「它」「他們」指什麼" in s and "不得把先前的回答當成證據" in s and "事實只能來自" in s


def test_no_history_means_no_history_block_and_the_same_message_as_before():
    post = FakePost()
    answer("問題", [PUB], post=post)
    assert "先前對話" not in user_of(post) and user_of(post) == "段落：\n[1] (甲科技 / 基本資料)\n公開事實ABC\n\n問題：問題"


def test_prior_answer_text_is_not_added_to_sources():
    r = answer("那薪水呢？", [PUB], post=FakePost(), history=HIST)
    assert r["sources"] == [{"company": "甲科技", "file": "01_甲科技.md", "heading_path": "基本資料"}]


def test_only_public_segments_and_history_are_sent():
    hits = search("刺蝟密語 FastAPI 面試 風險", corpus=MINI, k=50, method="bm25")
    post = FakePost()
    answer("那薪水呢？", hits, post=post, history=HIST)
    sent = sent_text(post)
    assert "刺蝟密語" not in sent and "珊瑚礁" not in sent and "離職率" not in sent
    assert "徵後端工程師" in sent  # 先前對話有送


# ---- 提示詞修正：可檢查的規則文字 ----
def test_overstatement_rule_text_is_in_the_system_prompt():
    for w in ("使用", "採用", "提供", "具備", "頁面", "介紹", "相關", "未說明關係", "不得"):
        assert w in SYSTEM, w
    assert "只陳述段落明確說公司" in SYSTEM


def test_nino_regression_prompt_carries_the_segment_and_the_rule_together():
    post = FakePost()
    answer("尼諾思的技術堆疊與開發工具有哪些？", [NINO], post=post)
    assert "AMD Vitis AI／FPGA／DPU 的頁面" in user_of(post)  # 容易被誤寫成「公司使用」的原句確實在證據裡
    assert "段落寫「頁面」「介紹」「相關」「未說明關係」時，不得當作公司已採用" in system_of(post)


def test_note_wording_rule_maps_internal_marks_to_plain_words():
    for w in ("資料中沒有提到", "（資料標註為推測）", "（公司自述）", "【推測】", "【自述】"):
        assert w in SYSTEM, w
    assert "不要照抄研究筆記的字眼" in SYSTEM


def test_not_found_contract_is_unchanged():
    assert "只回「查無」兩個字" in SYSTEM
    assert answer("問題", [], post=FakePost(), history=HIST) == {"answer": "查無", "sources": []}
    assert answer("問題", [PUB], post=FakePost(reply="查無"), history=HIST) == {"answer": "查無", "sources": []}

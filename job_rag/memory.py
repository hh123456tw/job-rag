"""對話記憶（票 22）。伺服器不存對話：前端每次請求帶最近 2 輪，這裡只做驗證、截斷與追問補全。
追問補全規則只寫在這個檔（expand），不用 LLM 改寫問句。"""
import json
import re

from .retrieval import mentions_company

MAX_TURNS = 2     # 最近 2 輪
MAX_QUESTION = 200
MAX_ANSWER = 300  # 每則答案截斷到 300 字
MAX_RAW = 4000    # history 參數原文長度上限；超過就拒絕（正常的 2 輪最多約 1000 字）
SHORT = 12        # 追問補全：問句（去頭尾空白）在這個字數以內才算「很短」
# 問句自帶這些主題詞，就是一個完整的新問題，不補全。「薪水」「出差」「資本額」這類細項不在其中：
# 它們單獨出現時常是追問（「那薪水呢？」）。AI 要當獨立單字比對，不能是 Rain 裡的 ai。
TOPIC = re.compile("做什麼|職缺|技術|營收|財務|新聞|產品|(?<![A-Za-z])AI(?![A-Za-z])", re.I)


class HistoryError(ValueError):
    """history 參數不合格。訊息直接回給前端。"""


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def clean_history(raw) -> list[dict]:
    """raw 是前端送來的 JSON 字串，內容不可信。回最近 MAX_TURNS 輪 [{"q","a"}]；不合格丟 HistoryError。"""
    if not raw:
        return []
    if not isinstance(raw, str) or len(raw) > MAX_RAW:
        raise HistoryError(f"對話記錄太長（上限 {MAX_RAW} 字）。")
    try:
        data = json.loads(raw)
    except ValueError:
        raise HistoryError("對話記錄格式不符。") from None
    if not isinstance(data, list) or not all(
            isinstance(t, dict) and isinstance(t.get("q"), str) and isinstance(t.get("a"), str) for t in data):
        raise HistoryError("對話記錄格式不符。")
    turns = [{"q": _flat(t["q"])[:MAX_QUESTION], "a": _flat(t["a"])[:MAX_ANSWER]} for t in data[-MAX_TURNS:]]
    return [t for t in turns if t["q"]]


def expand(question: str, history: list[dict], corpus=None) -> str:
    """追問補全：有上一題、問句在 SHORT 字以內、不含公司名、不含主題詞，就把上一題的使用者問句接在前面。
    只用上一題的問句，不用答案。其餘情況原樣回傳。"""
    q = question.strip()
    if history and len(q) <= SHORT and not TOPIC.search(q) and not mentions_company(q, corpus):
        return f"{history[-1]['q']} {q}"
    return q

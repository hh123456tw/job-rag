"""整理成答案：把公開事實段落交給 DeepSeek，回附出處的答案。LLM 呼叫只在這裡。"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.deepseek.com/chat/completions"  # https://api-docs.deepseek.com/
DEFAULT_MODEL = "deepseek-flash"  # 官方文件：由 DeepSeek-V4.1-Flash-1017 提供；可用 DEEPSEEK_MODEL 覆寫
NOT_FOUND = "查無"
TIMEOUT = 30
SYSTEM = (
    "你只能根據使用者提供的編號段落，用繁體中文白話回答問題。引用時標註段落編號，例如 [1]。"
    f"段落沒有答案時，只回「{NOT_FOUND}」兩個字，不要猜測或補充。"
)


class AnswerError(RuntimeError):
    """整理成答案失敗。訊息直接顯示給使用者。"""


def _post(url, headers, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode("utf-8"), headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _key(env_file) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and Path(env_file).is_file():
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            name, _, val = line.partition("=")
            if name.strip() == "DEEPSEEK_API_KEY":
                key = val.strip().strip("\"'")
    if not key:
        raise AnswerError("未設定 DEEPSEEK_API_KEY：請在 .env 填入金鑰")
    return key


def format_source(i: int, h: dict) -> str:
    """生成端看到的段落格式；評審端也用同一份，才算看到同樣的證據。"""
    return f"[{i}] ({h['company']} / {h['heading_path']})" + chr(10) + h["text"]


def answer(question: str, hits: list[dict], post=_post, env_file=".env") -> dict:
    """hits 來自 search()，只可能是公開事實段落。回 {"answer", "sources"}；失敗丟 AnswerError。"""
    used = hits
    if not used:
        return {"answer": NOT_FOUND, "sources": []}
    key = _key(env_file)
    context = (chr(10) * 2).join(format_source(i, h) for i, h in enumerate(used, 1))
    body = {
        "model": os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"段落：\n{context}\n\n問題：{question}"}],
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    try:
        resp = post(URL, {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, body, TIMEOUT)
    except urllib.error.HTTPError as e:
        why = {401: "金鑰錯誤", 402: "餘額不足"}.get(e.code, f"HTTP {e.code}")
        raise AnswerError(f"DeepSeek 回報錯誤：{why}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AnswerError(f"無法連到 DeepSeek（逾時或無網路）：{e}") from e
    try:
        text = resp["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise AnswerError("DeepSeek 回應格式不符") from e
    if not text or text == NOT_FOUND:
        return {"answer": NOT_FOUND, "sources": []}
    sources = []
    for h in used:  # 出處不重複：同一個位置的多個段落只列一次
        src = {k: h[k] for k in ("company", "file", "heading_path")}
        if src not in sources:
            sources.append(src)
    return {"answer": text, "sources": sources}

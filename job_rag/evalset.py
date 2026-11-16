"""評估題資料檔的檢查與人讀表。
python -X utf8 -m job_rag.evalset            # 檢查（需 JOB_RAG_CORPUS），印問題清單
python -X utf8 -m job_rag.evalset --write-md # 同時重寫 eval/questions.md
"""
import json
import re
from pathlib import Path

from .retrieval import _corpus_dir, _segments

PENDING = "待使用者確認"  # 只有使用者能改成已確認；程式與 AI 不改
REVIEW = "## 題目審查"
_HEAD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def sections(text: str) -> dict[str, str]:
    """標題路徑（不含 H1，以「 > 」連接，與 search() 的 heading_path 同格式）-> 該標題之下的全部文字（含子標題）。"""
    out: dict[str, list[str]] = {}
    stack: list[tuple[int, str]] = []
    open_paths: list[tuple[int, str]] = []  # 仍在收文字的標題
    for line in text.splitlines():
        m = _HEAD.match(line)
        if m:
            lv = len(m.group(1))
            while stack and stack[-1][0] >= lv:
                stack.pop()
            stack.append((lv, m.group(2)))
            open_paths = [(l, p) for l, p in open_paths if l < lv]
            if lv > 1:
                path = " > ".join(t for l, t in stack if l > 1)
                open_paths.append((lv, path))
                out.setdefault(path, [])
        else:
            for _, p in open_paths:
                out[p].append(line)
    return {p: "\n".join(v) for p, v in out.items()}


def _files(root: Path):
    return {f.name: f for f in root.rglob("*.md")}


def verify(questions: list[dict], corpus=None) -> list[str]:
    root = _corpus_dir(corpus)
    files = _files(root)
    all_text = {n: _squash(f.read_text(encoding="utf-8")) for n, f in files.items()}
    segs = _segments(str(root.resolve()))
    cache: dict[str, dict[str, str]] = {}
    probs, seen = [], set()
    for q in questions:
        qid = q.get("id", "?")
        bad = lambda msg: probs.append(f"{qid}：{msg}")
        if qid in seen:
            bad("題號重複")
        seen.add(qid)
        if q.get("status") != PENDING:
            bad(f"核對狀態必須是「{PENDING}」（只有使用者能確認）")
        if q["answerable"]:
            if not q["gold"]:
                bad("可回答題沒有金標")
            flags = set()
            for g in q["gold"]:
                if not g.get("quote"):
                    bad(f"金標 {g.get('file')} 缺佐證引文")
                    continue
                f = files.get(g["file"])
                if f is None:
                    bad(f"金標檔案不存在：{g['file']}")
                    continue
                secs = cache.setdefault(g["file"], sections(f.read_text(encoding="utf-8")))
                under = [t for p, t in secs.items() if p == g["heading"] or p.startswith(g["heading"] + " > ")]
                if g["heading"] not in secs:
                    bad(f"金標標題不存在：{g['file']} / {g['heading']}")
                elif not any(_squash(g["quote"]) in _squash(t) for t in under):
                    bad(f"引文不在金標標題之下：{g['file']} / {g['heading']}：{g['quote']}")
                flags |= {s["excluded"] for s in segs if s["file"] == g["file"] and
                          (s["heading_path"] == g["heading"] or s["heading_path"].startswith(g["heading"] + " > "))}
            if True in flags:
                bad("金標落在排除段落（金標只能是公開事實段落）")
        else:
            kws = q.get("absence_keywords") or []
            if q["gold"] or not kws:
                bad("不可回答題不能有金標，且必須列出查過的關鍵字")
            for kw in kws:
                hits = [n for n, t in all_text.items() if _squash(kw) in t]
                if hits:
                    bad(f"關鍵字「{kw}」在語料中找到：{hits[:3]}，答案可能在語料內")
    return probs


def to_markdown(questions: list[dict]) -> str:
    esc = lambda s: s.replace("|", "｜").replace("\n", " ")
    rows = ["| 編號 | 題目 | 類型 | 金標檔案與標題 | 佐證 | 核對狀態 |", "|---|---|---|---|---|---|"]
    for q in questions:
        kind = q["type"]
        if q["answerable"]:
            gold = "<br>".join(f"{g['file']} ／ {g['heading']}" for g in q["gold"])
            ev = "<br>".join(f"「{g['quote']}」" for g in q["gold"])
        else:
            gold = "（無，答案不在語料）"
            ev = "全語料搜尋查無：" + "、".join(q["absence_keywords"])
        rows.append(f"| {q['id']} | {esc(q['question'])} | {kind} | {esc(gold)} | {esc(ev)} | {q['status']} |")
    return "\n".join(rows) + "\n"


def type_summary(questions: list[dict]) -> str:
    from collections import Counter
    return "、".join(f"{k} {n}" for k, n in Counter(q["type"] for q in questions).items())


def main():
    import sys
    qs = json.loads(Path("eval/questions.json").read_text(encoding="utf-8"))["questions"]
    probs = verify(qs)
    print(f"{len(qs)} 題；問題 {len(probs)} 個")
    for p in probs:
        print(" -", p)
    if "--write-md" in sys.argv:
        head = ("# 評估題（30 題）\n\n由 `eval/questions.json` 產生，勿手改。\n"
                "核對狀態「待使用者確認」＝AI 已用程式核對引文，但使用者尚未逐題對照原檔。\n\n")
        md = Path("eval/questions.md")
        keep = ""  # 手寫的「題目審查」一節不被重寫洗掉
        if md.exists() and REVIEW in (old := md.read_text(encoding="utf-8")):
            keep = "\n" + old[old.index(REVIEW):]
        md.write_text(head + to_markdown(qs) + keep, encoding="utf-8")
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()

"""自用資料：面經檔 selfdata/面經/**/*.jsonl（票 24）。容錯載入：欄位缺、壞行、被鎖、窗口不明的篇一律略過。
只收 window_ok 為真、未被鎖、內文非空的篇。內容只存在記憶體與 .cache/ 的向量，不寫進任何被追蹤的檔案。"""
import json
import os
from functools import lru_cache
from pathlib import Path

from .retrieval import _pieces

LABEL = {"goodjob.life": "GoodJob", "interview.tw": "面試趣"}


def self_dir() -> Path:
    return Path(os.environ.get("JOB_RAG_SELF_DIR") or Path(__file__).resolve().parent.parent / "selfdata")


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _qa(items) -> str:
    out = []
    for x in items if isinstance(items, list) else []:
        if isinstance(x, dict):
            q, a = _s(x.get("q") or x.get("question")), _s(x.get("a") or x.get("answer"))
            if q or a:
                out.append(f"問：{q}\n答：{a}" if a else f"問：{q}")
        elif _s(x):
            out.append(_s(x))
    return "\n".join(out)


def _sections(r: dict) -> list[tuple[str, str]]:
    """(小標, 內文)。goodjob 用 sections 與 interview_qas；面試趣用 process_text 與 qa。"""
    out = []
    for s in r.get("sections") if isinstance(r.get("sections"), list) else []:
        if isinstance(s, dict) and _s(s.get("content")):
            out.append((_s(s.get("subtitle")), _s(s["content"])))
    if _s(r.get("process_text")):
        out.append(("面試過程", _s(r["process_text"])))
    for key in ("interview_qas", "qa"):
        if t := _qa(r.get(key)):
            out.append(("面試題目", t))
    return out


def _company(stem: str, r: dict, names) -> str | None:
    if stem in names:
        return stem
    field = _s(r.get("company")) + _s(r.get("original_company_name"))
    hits = [n for n in names if n in field]
    return hits[0] if len(hits) == 1 else None


def _articles(d, names):
    """(公司, 標題, [(小標, 內文)], 結果)。"""
    root = Path(d, "面經")
    for f in sorted(root.rglob("*.jsonl")) if root.is_dir() else []:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("window_ok") is not True or r.get("locked") is True:
                continue
            secs, company = _sections(r), _company(f.stem, r, names)
            if not secs or not company:
                continue
            when = _s(r.get("interview_time")) or _s(r.get("interview_month")) or _s(r.get("share_date"))[:7]
            job = _s(r.get("job_title")) or _s(r.get("position")) or "職稱不明"
            title = f"面經（{LABEL.get(_s(r.get('source')), '面經')}）｜{when or '日期不明'}｜{job}"
            yield company, title, secs, _s(r.get("result"))


def load_interviews(d, names) -> list[dict]:
    """面經段落（皆為私人）。names 是索引裡已有的公司名。"""
    segs = []
    for company, title, secs, result in _articles(d, names):
        for i, (sub, text) in enumerate(secs):
            head = f"{title} > {sub}" if sub else title
            for j, piece in enumerate(_pieces(text)):
                if i == 0 and j == 0 and result:
                    piece = f"結果：{result}\n{piece}"
                segs.append({"company": company, "file": "面經", "heading_path": head, "excluded": True, "private": True,
                             "source": "面經", "text": piece, "_index": f"{company} {head}\n{piece}", "_title": head})
    return segs


def article_counts(d, names) -> dict[str, int]:
    out: dict[str, int] = {}
    for company, *_ in _articles(d, names):
        out[company] = out.get(company, 0) + 1
    return out


@lru_cache(maxsize=8)
def article_counts_cached(d: str, names: tuple) -> dict:
    """提示卡用：每次開頁都數一次會重讀所有面經檔，所以快取（鍵含資料夾與公司清單）。"""
    return article_counts(d, set(names))

"""對話頁的「我能回答什麼」提示（票 21）：主題與筆數全部由載入的公開段落計算，不手寫。"""
import re

from .retrieval import NOT_COLLECTED, _public, _root

# 白話主題 -> 標題路徑要含的關鍵字之一（任何一層標題含關鍵字即算）。順序即顯示順序。
JOB = "職缺資料"  # 標題含「職缺」，或來自跨公司的 104 職缺檔（檔名不是「兩位數字_」開頭）；None 是佔位，筆數另算
TOPICS = [("公司簡介", ("基本資料",)), ("業務與財務", ("業務", "財務")), ("部門在做什麼", ("在做什麼",)),
          (JOB, None), ("技術堆疊", ("技術堆疊",)), ("近期新聞", ("新聞",))]
# 常被問、但專案不一定收的主題。薪資與員工人數只在語料真的有數字時才算「有」；NOT_COLLECTED 那類段落專案一律不收。
SALARY = re.compile(r"(月薪|年薪|時薪)\s*[:：約]?\s*\d")  # 「待遇面議」不算：沒有數字
HEADCOUNT = re.compile(r"(員工(人數|數)?|規模(區間)?)[\s|:：]*約?\s*\d")  # 「應徵人數」「人數：6~10 人」是徵才人數，不算


def _is_job(s) -> bool:
    return "職缺" in s["heading_path"] or not re.match(r"\d\d_", s["file"])


# 自用模式才有的主題：標題含關鍵字的私人筆記段落。順序即顯示順序。
PRIVATE_TOPICS = [("面談作戰卡", ("作戰",)), ("你的對應", ("對應",)), ("風險與判斷", ("風險", "判斷", "推測", "限制", "未查到")),
                  ("面試與評價", ("面試", "評價"))]


def topics(company: str | None = None, corpus=None, mode: str = "demo") -> dict:
    """company 為 None 時統計全部公司。回 {"segments", "have": [文字], "missing": [文字]}。
    mode="self" 時多回 "private_have"（私人筆記主題）與 "interviews"（面經篇數）；公開主題的統計不變，不再把「面試與評價」列為沒有。"""
    allsegs = [s for s in _public(_root(corpus, mode)) if company is None or s["company"] == company]
    segs = [s for s in allsegs if not s.get("private")]
    jobs = sum(_is_job(s) for s in segs)
    have = [f"{t}（{jobs} 段）" if t == JOB else t for t, kws in TOPICS
            if (jobs if kws is None else any(k in s["heading_path"] for s in segs for k in kws))]
    missing = []
    if not any(SALARY.search(s["text"]) for s in segs):
        missing.append("薪資範圍")
    if not any(HEADCOUNT.search(s["text"]) for s in segs):
        missing.append("員工人數")
    if mode == "demo":
        missing.append(NOT_COLLECTED)
        return {"segments": len(segs), "have": have, "missing": missing}
    notes = [s for s in allsegs if s.get("source") == "筆記"]
    from .selfdata import article_counts_cached, self_dir
    n = article_counts_cached(str(self_dir()), tuple(sorted({s["company"] for s in _public(_root(corpus)) if s["company"] != "綜合"})))
    return {"segments": len(segs), "have": have, "missing": missing,
            "interviews": n.get(company, 0) if company else sum(n.values()),
            "private_have": [t for t, kws in PRIVATE_TOPICS if any(k in s["heading_path"] for s in notes for k in kws)]}

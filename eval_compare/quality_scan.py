"""段落品質掃描（不載入模型）。python -X utf8 eval_compare/quality_scan.py > eval_compare/quality_scan.txt"""
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from job_rag import retrieval as r  # noqa: E402

CORP = {"old": r"C:\claude\aipe04期末\履歷\廠商深查", "new": r"C:\claude\aipe04期末\履歷\廠商深查_新版"}


def is_job(s):
    return bool(re.match(r"^3\d_", s["file"])) or not re.match(r"^\d\d_", s["file"]) or "職缺" in s["heading_path"]


def table_only(t):
    lines = [l for l in t.splitlines() if l.strip()]
    return bool(lines) and all(l.lstrip().startswith("|") for l in lines)


def url_only(t):
    rest = re.sub(r"https?://\S+", "", t)
    rest = re.sub(r"[\s\-\*\|：:（）()來源網址]+", "", rest)
    return "http" in t and len(rest) < 8


for v, p in CORP.items():
    segs = [s for s in r._segments(str(r._corpus_dir(p).resolve())) if not s["excluded"]]
    L = [len(s["text"]) for s in segs]
    print(f"===== {v}：公開段落 {len(segs)}；字數 中位數 {statistics.median(L):.0f}、平均 {statistics.mean(L):.0f}、最小 {min(L)}、最大 {max(L)}")
    print("最短 5：")
    for s in sorted(segs, key=lambda s: len(s["text"]))[:5]:
        print(f"  {len(s['text'])} 字 [{s['company']}|{s['file'][:22]}|{s['heading_path'][-40:]}] {s['text'][:50]!r}")
    print("最長 5：")
    for s in sorted(segs, key=lambda s: -len(s["text"]))[:5]:
        print(f"  {len(s['text'])} 字 [{s['company']}|{s['file'][:22]}|{s['heading_path'][-40:]}]")
    t = [s for s in segs if table_only(s["text"])]
    u = [s for s in segs if url_only(s["text"])]
    short = [s for s in segs if len(s["text"]) < 60]
    print(f"純表格段 {len(t)}；只有網址段 {len(u)}；少於 60 字 {len(short)}")
    for s in (t + u)[:8]:
        print(f"  {'表格' if s in t else '網址'} [{s['company']}|{s['file'][:22]}|{s['heading_path'][-30:]}] {len(s['text'])}字")
    tot, job = Counter(s["company"] for s in segs), Counter(s["company"] for s in segs if is_job(s))
    print("公司 | 段落 | 職缺段 | 職缺佔比")
    for c in sorted(tot, key=lambda c: -tot[c]):
        print(f"  {c} | {tot[c]} | {job[c]} | {job[c] / tot[c]:.0%}")
    print(f"  合計 | {len(segs)} | {sum(job.values())} | {sum(job.values()) / len(segs):.0%}")
    # 同一職缺是否在新版內重複出現（104 檔舊段與 30～37 並存）：用職缺網址代碼統計
    codes = Counter()
    for s in segs:
        for m in set(re.findall(r"104\.com\.tw/job/(\w+)", s["text"])):
            codes[(s["company"], m)] += 1
    multi = [(k, n) for k, n in codes.items() if n > 1]
    print(f"職缺網址代碼：不重複 {len(codes)} 個；出現在 2 段以上 {len(multi)} 個")
    byco = Counter(k[0] for k, n in multi)
    print("  重複代碼數（依公司）：", dict(byco))
    # 新舊並存：同一代碼出現在 30～37 檔與舊 104 檔
    both = Counter()
    byf = {}
    for s in segs:
        for m in set(re.findall(r"104\.com\.tw/job/(\w+)", s["text"])):
            byf.setdefault((s["company"], m), set()).add("new" if re.match(r"^3\d_", s["file"]) else "old")
    for k, kinds in byf.items():
        if kinds == {"new", "old"}:
            both[k[0]] += 1
    print("  同一代碼同時出現在 30～37 檔與舊檔：", dict(both))

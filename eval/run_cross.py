"""票 31 跨公司評估：python -X utf8 eval/run_cross.py
需要 JOB_RAG_CORPUS、JOB_RAG_MODELS。不呼叫任何 LLM。對 PER_COMPANY = 1、2、3 各跑 15 題，
量：各家涵蓋率（相關公司中，取到的段落含關鍵字的比例）、送進 LLM 的段數與字數、/api/search 耗時；
並列出每題的最高分，供挑 CROSS_FLOOR。寫入 eval/results_cross.txt 與 eval/results_cross.json。"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402
from job_rag import retrieval  # noqa: E402

QFILE = ROOT / "eval" / "questions_cross.json"
TOKEN_PER_CHAR = 0.7  # 估計值：繁中約 0.6–0.8 token／字；沒有用 DeepSeek 分詞器量，只當量級


def has(text, kws):
    return any(k.lower() in text.lower() for k in kws)


def main():
    raw = QFILE.read_bytes()
    qs = json.loads(raw.decode("utf-8"))["questions"]
    live = {n for _, n in app._company_buttons()}
    all_segs = list(retrieval._public(retrieval._root(None, "demo")))
    segs = [s for s in all_segs if s["company"] in live]
    c = app.app.test_client()
    out = {"floor": retrieval.CROSS_FLOOR, "per_default": retrieval.PER_COMPANY, "digest": hashlib.sha1(raw).hexdigest()[:16],
           "tokens_per_char": TOKEN_PER_CHAR, "n_companies": len(live), "index_companies": len({s["company"] for s in all_segs}),
           "tops": {}, "per": {}}
    rel = {}
    for q in qs:
        rel[q["id"]] = sorted({s["company"] for s in segs if has(s["text"], q["keywords"])})
        n_all = sum(has(s["text"], q["keywords"]) for s in all_segs)
        if not q["answerable"] and n_all:
            sys.exit(f"{q['id']} 標為不可回答，但語料有 {n_all} 段含關鍵字")
    out["relevant"] = rel
    for per in (1, 2, 3):
        retrieval.PER_COMPANY = per
        rows = []
        for q in qs:
            ms = []
            for _ in range(3):  # 同一題量 3 次取中位數
                d = c.get("/api/search", query_string={"q": q["question"]}).get_json()
                ms.append(d["search_ms"])
            assert d["cross"] is True, q["question"]
            hits = d["hits"]
            top = max(h["score"] for h in hits)
            out["tops"][q["id"]] = top
            got = {h["company"] for h in hits if has(h["text"], q["keywords"])}
            n_rel = len(rel[q["id"]])
            n_ok = len(got & set(rel[q["id"]]))
            chars = sum(len(h["text"]) for h in hits)
            rows.append({"id": q["id"], "answerable": q["answerable"], "status": d["status"], "n_hits": len(hits),
                         "companies": len({h["company"] for h in hits}), "n_relevant": n_rel, "n_correct": n_ok,
                         "coverage": (n_ok / n_rel) if n_rel else None, "chars": chars,
                         "est_tokens": round(chars * TOKEN_PER_CHAR), "ms": statistics.median(ms), "top": top})
        out["per"][per] = rows
    (ROOT / "eval/results_cross.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = render(qs, out)
    (ROOT / "eval/results_cross.txt").write_text(text, encoding="utf-8")
    print(text)


def passed(r):
    return (r["status"] == "ok" and r["n_correct"] > 0) if r["answerable"] else r["status"] == "low"


def render(qs, out):
    L = [f"跨公司評估（票 31）。現場 {out['n_companies']} 家（索引共 {out['index_companies']} 家公司）；題檔 eval/questions_cross.json（摘要 {out['digest']}）。",
         f"CROSS_FLOOR = {out['floor']}；預設 PER_COMPANY = {out['per_default']}。",
         "通過：可回答題＝狀態 ok 且至少一家相關公司的段落含關鍵字；不可回答題＝狀態 low。",
         "相關公司：由程式對載入的公開段落做關鍵字比對，不是人工逐段標註（會漏同義說法，也會把只是提到的段落算進去）。", ""]
    r1 = out["per"][1]
    ans = [r for r in r1 if r["answerable"]]
    un = [r for r in r1 if not r["answerable"]]
    L.append(f"每題最高分（與每家段數無關）：可回答題最低 {min(r['top'] for r in ans):.3f}，不可回答題最高 {max(r['top'] for r in un):.3f}")
    for per, rows in out["per"].items():
        L += ["", f"== 每家取 {per} 段 ==",
              "題號 通過 公司數 段數 相關家數 含關鍵字家數 涵蓋率 字數 估token 毫秒 最高分 問句"]
        for r, q in zip(rows, qs):
            cv = "-" if r["coverage"] is None else f"{r['coverage']:.2f}"
            L.append(f"{r['id']} {'是' if passed(r) else '否'} {r['companies']} {r['n_hits']} {r['n_relevant']} {r['n_correct']} {cv} "
                     f"{r['chars']} {r['est_tokens']} {r['ms']} {r['top']:.3f} {q['question']}")
        a = [r for r in rows if r["answerable"]]
        cvs = [r["coverage"] for r in a if r["coverage"] is not None]
        L.append(f"通過 {sum(passed(r) for r in rows)}/{len(rows)}（可回答 {sum(passed(r) for r in a)}/{len(a)}，"
                 f"不可回答 {sum(passed(r) for r in rows if not r['answerable'])}/{len(rows) - len(a)}）；"
                 f"平均涵蓋率 {sum(cvs) / len(cvs):.3f}；可回答題平均 {statistics.mean(r['chars'] for r in a):.0f} 字"
                 f"（約 {statistics.mean(r['est_tokens'] for r in a):.0f} token，估計）；/api/search 耗時中位數 {statistics.median(r['ms'] for r in rows)} 毫秒")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()

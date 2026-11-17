"""新舊語料比較的檢索評估（不呼叫 LLM、不寫 eval/results_*）。
python -X utf8 eval_compare/run_version.py old|new
環境變數：JOB_RAG_CORPUS、JOB_RAG_MODELS、JOB_RAG_CACHE 由呼叫者設。輸出 eval_compare/res_<ver>.json。
舊版用原題檔 eval/*.json；新版用 eval_compare/*_new.json（只改 gold）。"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import run_real  # noqa: E402
import app  # noqa: E402
from job_rag import retrieval  # noqa: E402
from job_rag.evaluate import DEPTH, evaluate  # noqa: E402
from job_rag.stats import metric_interval  # noqa: E402

VER = sys.argv[1]
assert VER in ("old", "new")
HERE = Path(__file__).parent


def qpath(name):
    return (HERE / f"{name}_new.json") if VER == "new" else (ROOT / "eval" / f"{name}.json")


def load(p):
    return json.loads(Path(p).read_bytes().decode("utf-8"))["questions"]


def is_job(s):
    f = s["file"]
    return bool(re.match(r"^3\d_", f)) or not re.match(r"^\d\d_", f) or "職缺" in s["heading_path"]


def plain_eval(name, split_cross):
    qs = load(qpath(name))
    routes = {q["id"]: run_real.route(q) for q in qs}
    cross_qs = [q for q in qs if split_cross and routes[q["id"]] == "跨公司"]
    plain = [q for q in qs if q not in cross_qs]
    ans = {q["id"] for q in plain if q["answerable"]}
    rep = evaluate(plain, method="bge-m3", detect=True, dedupe=True)["scores"]
    top, ranks = rep["gate_scores"], rep["ranks"]
    rl = list(ranks.values())
    ci = {k: list(metric_interval(rl, k)) for k in ("hit@1", "hit@3", "hit@5", "mrr")}
    T, TS = retrieval.NOT_FOUND_THRESHOLD, round(retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP, 3)
    gt = rep["gate"]
    out = {"n": len(qs), "n_plain": len(plain), "n_cross": len(cross_qs), "metrics": rep["metrics"], "ci": ci, "ranks": ranks,
           "scores": top, "routes": routes, "scoped": rep["scoped"], "answerable": sorted(ans),
           "gate_current": {"blocked_u": gt["unanswerable_blocked"], "passed_u": gt["unanswerable_passed"],
                            "blocked_a": gt["answerable_blocked"]},
           "thr": {"plain": T, "scoped": TS},
           "cross": run_real.cross_rows(cross_qs) if cross_qs else [],
           "text": {q["id"]: q["question"] for q in qs}}
    return out


def probe(q):
    """與網站相同的分流；回前 5 名摘要。"""
    question = q["question"]
    co = None
    if retrieval.is_cross(question):
        hits = app._cross_hits(question, "demo")
        low = app._low_cross(hits)
        thr = retrieval.CROSS_FLOOR
        route = "跨公司"
    else:
        co = retrieval.detect_company(question)
        hits = retrieval.search(question, company=co, gate=False, dedupe=True)
        low = app._low(hits, co)
        thr = app._thr(co)
        route = "單公司:" + co if co else "未指定"
    segs = {(s["file"], s["heading_path"], s["text"]): s for s in retrieval._public(retrieval._root(None, "demo"))}
    rows = []
    for h in hits[:5]:
        s = segs[(h["file"], h["heading_path"], h["text"])]
        rows.append({"company": h["company"], "file": h["file"], "heading": h["heading_path"], "score": round(h["score"], 4),
                     "job": is_job(s), "text": h["text"][:400]})
    top = max((h["score"] for h in hits), default=None)
    return {"id": q["id"], "question": question, "route": route, "top": top, "threshold": thr, "low": low,
            "n_job_top5": sum(r["job"] for r in rows), "hits": rows}


def main():
    res = {"version": VER, "corpus": retrieval._corpus_dir(None).name, "n_public": len(retrieval._public(retrieval._root(None, "demo")))}
    res["q30"] = plain_eval("questions", False)
    res["q40"] = plain_eval("questions_heldout", True)
    res["real20"] = plain_eval("questions_real", True)
    # 跨公司題（questions_cross.json，兩邊同一份，沒有 gold）
    qs = load(ROOT / "eval" / "questions_cross.json")
    live = {n for _, n in app._company_buttons()}
    all_segs = list(retrieval._public(retrieval._root(None, "demo")))
    segs = [s for s in all_segs if s["company"] in live]
    has = run_real.has
    cross = {}
    for per in (1, 2, 3):
        retrieval.PER_COMPANY = per
        c = app.app.test_client()
        rows = []
        for q in qs:
            d = c.get("/api/search", query_string={"q": q["question"]}).get_json()
            hits = d["hits"]
            top = max(h["score"] for h in hits)
            rel = sorted({s["company"] for s in segs if has(s["text"], q["keywords"])})
            got = sorted({h["company"] for h in hits if has(h["text"], q["keywords"])} & set(rel))
            ok = (d["status"] == "ok" and bool(got)) if q["answerable"] else d["status"] == "low"
            rows.append({"id": q["id"], "answerable": q["answerable"], "status": d["status"], "cross": d["cross"], "top": top,
                         "n_relevant": len(rel), "n_correct": len(got), "coverage": (len(got) / len(rel)) if rel else None, "pass": ok})
        cross[per] = rows
    retrieval.PER_COMPANY = 2
    res["cross15"] = cross
    res["gap"] = [probe(q) for q in load(HERE / "gap_questions.json")]
    res["job"] = [probe(q) for q in load(HERE / "job_questions.json")]
    # 全部不可回答題的原始最高分也存（污染題後續用）
    (HERE / f"res_{VER}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", VER, res["n_public"])


main()

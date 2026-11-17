"""per=2 vs per=3 端到端比較。python -X utf8 eval_per3/run.py（需 JOB_RAG_CORPUS/MODELS/CACHE）。
照 app.py /api/answer 跨公司路徑：_is_cross -> _cross_hits(per 由 retrieval.PER_COMPANY 控制) -> _low_cross -> answer(cross=True)。
每題每設定只呼叫一次，無重試；結果邊跑邊存，重跑會略過已完成項。"""
import json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402  (不啟動暖機：start_warmup 只在 __main__)
from job_rag import retrieval  # noqa: E402
from job_rag.answer import answer, _post, AnswerError  # noqa: E402

OUT = ROOT / "eval_per3" / "results.json"
qs = json.loads((ROOT / "eval/questions_cross.json").read_text(encoding="utf-8"))["questions"]
live = {n for _, n in app._company_buttons()}
segs = [s for s in retrieval._public(retrieval._root(None, "demo")) if s["company"] in live]
has = lambda t, kws: any(k.lower() in t.lower() for k in kws)
NOANS = re.compile(r"查無|資料沒寫|資料中沒有提到|沒有提到|未提及")
res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
for q in qs:
    rel = sorted({s["company"] for s in segs if has(s["text"], q["keywords"])})
    for per in (2, 3):
        key = f"{q['id']}_per{per}"
        if key in res:
            continue
        retrieval.PER_COMPANY = per
        rq = q["question"]
        assert app._is_cross(rq, None, "demo"), rq
        hits = app._cross_hits(rq, "demo")
        r = {"id": q["id"], "per": per, "question": rq, "answerable": q["answerable"], "relevant": rel,
             "n_hits": len(hits), "top": max((h["score"] for h in hits), default=None),
             "blocked": app._low_cross(hits),
             "hits": [{"company": h["company"], "heading_path": h["heading_path"], "score": round(h["score"], 3), "text": h["text"]} for h in hits]}
        if not r["blocked"]:
            t0 = time.perf_counter()
            try:
                a = answer(rq, hits, post=_post, history=None, cross=True)
                r["answer"] = a["answer"]; r["usage"] = a.get("usage", {})
            except AnswerError as e:
                r["error"] = str(e)
            r["secs"] = round(time.perf_counter() - t0, 2)
            ans = r.get("answer", "")
            r["chars"] = len(ans)
            r["mentioned"] = sorted(c for c in live if c in ans)
            r["missed"] = sorted(set(rel) - set(r["mentioned"]))
            r["refuse"] = bool(NOANS.search(ans)) and (ans.strip() == "查無")
            r["has_nodata_phrase"] = bool(NOANS.search(ans))
        res[key] = r
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(key, r["n_hits"], r["blocked"], r.get("usage"), r.get("secs"), flush=True)

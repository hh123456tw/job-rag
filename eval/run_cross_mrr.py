"""跨公司路徑的「各家 MRR」：python -X utf8 eval/run_cross_mrr.py
跨公司題沒有唯一的金標段落，所以不能照一般檢索算 MRR。這裡的算法：
  對每一題的每一家「該出現的公司」（公開段落含關鍵字的公司），看那一家的段落照挑段名次排下來，
  第一個含關鍵字的段落排第幾名（只看到前 DEPTH 名，更後面算 0）；取倒數後，對所有（題, 公司）取平均。
兩種挑段名次都算：混合（BM25＋bge-m3，RRF；網站現行）與只用 bge-m3（對照）。
題目：eval/questions_heldout.json 裡走跨公司路徑的有答案題。只量不調，不呼叫 LLM，不套查無門檻。
同時算「前 PER_COMPANY 名內有含關鍵字段落的公司數」，應與 eval/results_heldout.json 的取到家數一致（自我檢查）。
寫 eval/results_cross_mrr.json／.txt。需要 JOB_RAG_CORPUS、JOB_RAG_MODELS。"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
import app  # noqa: E402
import run_real  # noqa: E402
from job_rag import retrieval as R  # noqa: E402
from job_rag.evaluate import DEPTH, questions_digest  # noqa: E402

OUT = ROOT / "eval" / "results_cross_mrr"


def main():
    qs = json.loads((ROOT / "eval/questions_heldout.json").read_bytes().decode("utf-8"))["questions"]
    cross = [q for q in qs if q["answerable"] and run_real.route(q) == "跨公司"]
    root = R._root(None, "demo")
    live = {n for _, n in app._company_buttons()}
    rows, rr = [], {"hybrid": [], "bge-m3": []}
    for q in cross:
        pool, rv = R._rank_vector(root, "bge-m3", q["question"], None)
        _, rb = R._rank_bm25(root, q["question"], None)
        orders = {"bge-m3": [i for i, _ in rv], "hybrid": [i for i, _ in R.rrf([[i for i, _ in rb], [i for i, _ in rv]])]}
        rel = sorted({s["company"] for s in pool if s["company"] in live and run_real.has(s["text"], q["keywords"])})
        row = {"id": q["id"], "n_relevant": len(rel), "ranks": {}}
        for m, order in orders.items():
            ranks = {}
            for c in rel:
                mine = [i for i in order if pool[i]["company"] == c]
                r = next((n for n, i in enumerate(mine[:DEPTH], 1) if run_real.has(pool[i]["text"], q["keywords"])), None)
                ranks[c] = r
                rr[m].append(1 / r if r else 0.0)
            row["ranks"][m] = ranks
        rows.append(row)
    per = R.PER_COMPANY
    out = {"date": datetime.date.today().isoformat(), "digest": questions_digest(qs), "n_questions": len(cross), "n_pairs": len(rr["hybrid"]),
           "depth": DEPTH, "per_company": per, "rows": rows, "methods": {}}
    for m in rr:
        got = sum(r is not None and r <= per for row in rows for r in row["ranks"][m].values())
        first = sum(r == 1 for row in rows for r in row["ranks"][m].values())
        out["methods"][m] = {"mrr": sum(rr[m]) / len(rr[m]), "first": first, "within_per": got}
    held = json.loads((ROOT / "eval/results_heldout.json").read_text(encoding="utf-8"))
    out["check_within_per_matches_results_heldout"] = out["methods"]["hybrid"]["within_per"] == sum(x["n_correct"] for x in held["cross"] if x["answerable"])
    OUT.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    name = {"hybrid": "混合（BM25＋bge-m3，網站現行）", "bge-m3": "只用 bge-m3（對照）"}
    L = [f"跨公司路徑的各家 MRR。題檔 eval/questions_heldout.json（摘要 {out['digest'][:16]}）；量測日期 {out['date']}。",
         f"有答案的跨公司題 {out['n_questions']} 題，該出現的公司共 {out['n_pairs']} 家次。每家只看前 {out['depth']} 名；不套查無門檻。",
         "算法：每一家該出現的公司，第一個含關鍵字的段落在那一家裡排第幾名，取倒數後平均。這不是一般檢索的 MRR（跨公司題沒有唯一的金標段落）。", "",
         f"挑段名次　各家 MRR　排第 1 名的家次　前 {per} 名內的家次"]
    for m, v in out["methods"].items():
        L.append(f"{name[m]}　{v['mrr']:.3f}　{v['first']}/{out['n_pairs']}　{v['within_per']}/{out['n_pairs']}")
    L += ["", f"自我檢查：混合的「前 {per} 名內的家次」與 eval/results_heldout.json 的取到家數一致：{'是' if out['check_within_per_matches_results_heldout'] else '否'}",
          "", "== 限制 ==", "「含關鍵字」是字面比對，換說法的題會吃虧，也偏向 BM25。這 10 題已用來調過跨公司門檻與挑段方式，數字偏樂觀。題目由單一模型出，沒有人工確認。"]
    OUT.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()

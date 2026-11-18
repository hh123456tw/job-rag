"""票 43、44：獨立測試題 100 題裡「走一般檢索的可回答題」，比較三種找法：python -X utf8 eval/run_heldout_methods.py
  bge-m3（網站現行）、hybrid（BM25＋bge-m3，RRF）、bge-m3 取前 CAND 段再用 bge-reranker-v2-m3 重排。
只量不調：設定與網站預設相同（公司名自動偵測開、去重開）；名次最多看到 DEPTH；不套查無門檻；不呼叫 LLM。
跨公司路徑的題不在這裡（那條路徑每家各取幾段，不是單一排名）。重排只存在這支評估程式，網站沒有接。
需要 JOB_RAG_CORPUS、JOB_RAG_MODELS（含 bge-reranker-v2-m3；缺就報錯，不補數字）。寫 eval/results_heldout_methods.txt／.json。"""
import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
import run_real  # noqa: E402
from job_rag import retrieval  # noqa: E402
from job_rag.evaluate import DEPTH, _asked, hit_rank, metrics, questions_digest  # noqa: E402
from job_rag.stats import metric_interval, paired_metric_interval, verdict  # noqa: E402

QFILE = ROOT / "eval" / "questions_heldout.json"
OUT = ROOT / "eval" / "results_heldout_methods"
CAND = 20  # 重排的候選段數（bge-m3 前 20 段）；沒有調過，只試這一個值
RERANKER = "bge-reranker-v2-m3"
KINDS = ("hit@1", "hit@3", "hit@5", "mrr")


def rerank(model, question, hits):
    """用 cross-encoder 對 (問句, 段落) 逐對打分，分數高的在前。"""
    s = model.predict([(question, f"{h['company']} {h['heading_path']}\n{h['text']}") for h in hits], batch_size=8)
    return [h for _, h in sorted(zip(s, hits), key=lambda x: -x[0])]


def main():
    from sentence_transformers import CrossEncoder
    mdir = Path(os.environ["JOB_RAG_MODELS"]) / RERANKER
    if not (mdir / "model.safetensors").is_file():
        raise SystemExit(f"找不到重排模型：{mdir}")
    qs = json.loads(QFILE.read_bytes().decode("utf-8"))["questions"]
    plain = [q for q in qs if q["answerable"] and run_real.route(q) != "跨公司"]
    ce = CrossEncoder(str(mdir), max_length=512)
    ranks = {"bge-m3": {}, "hybrid": {}, "rerank": {}}
    secs = {"bge-m3": 0.0, "hybrid": 0.0, "rerank": 0.0}
    for n, q in enumerate(plain, 1):
        co = q.get("company") or retrieval.detect_company(q["question"])
        kw = dict(company=co, gate=False, dedupe=True)
        for m in ("bge-m3", "hybrid"):
            t = time.perf_counter()
            ranks[m][q["id"]] = hit_rank(retrieval.search(q["question"], method=m, k=DEPTH, **kw), q["gold"])
            secs[m] += time.perf_counter() - t
        t = time.perf_counter()
        cand = retrieval.search(q["question"], method="bge-m3", k=CAND, **kw)
        ranks["rerank"][q["id"]] = hit_rank(rerank(ce, _asked(q["question"], co), cand)[:DEPTH], q["gold"])
        secs["rerank"] += time.perf_counter() - t
        print(n, q["id"], {m: ranks[m][q["id"]] for m in ranks}, flush=True)
    ids = [q["id"] for q in plain]
    base = [ranks["bge-m3"][i] for i in ids]
    out = {"date": datetime.date.today().isoformat(), "digest": questions_digest(qs), "n": len(plain), "depth": DEPTH, "cand": CAND,
           "reranker": RERANKER, "device": str(getattr(ce, "device", "cpu")), "ranks": ranks, "methods": {}}
    for m in ranks:
        r = [ranks[m][i] for i in ids]
        out["methods"][m] = {**{k: metrics(r)[k] for k in KINDS}, "ci": {k: list(metric_interval(r, k)) for k in KINDS},
                             "sec_per_question": secs[m] / len(plain)}
        if m != "bge-m3":
            out["methods"][m]["diff_vs_bge_m3"] = {k: {"diff": metrics(r)[k] - metrics(base)[k], "ci": list(paired_metric_interval(r, base, k))}
                                                   for k in ("hit@3", "mrr")}
            out["methods"][m]["better"] = [i for i in ids if (ranks[m][i] or 99) < (ranks["bge-m3"][i] or 99)]
            out["methods"][m]["worse"] = [i for i in ids if (ranks[m][i] or 99) > (ranks["bge-m3"][i] or 99)]
    OUT.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = render(out)
    OUT.with_suffix(".txt").write_text(text, encoding="utf-8")
    print(text)


def render(o):
    name = {"bge-m3": "bge-m3（網站現行）", "hybrid": "hybrid（BM25＋bge-m3）", "rerank": f"bge-m3 前 {o['cand']} 段＋{o['reranker']} 重排"}
    L = [f"獨立測試題：三種找法比較。題檔 eval/questions_heldout.json（摘要 {o['digest'][:16]}）；量測日期 {o['date']}。",
         f"只算走一般檢索的可回答題 {o['n']} 題（跨公司路徑的題不在內）。公司名自動偵測開、去重開；名次最多看到 {o['depth']}；不套查無門檻。",
         f"重排只試一種設定（候選 {o['cand']} 段），沒有調過；重排只存在評估程式，網站沒有接。運算裝置 {o['device']}。", "",
         "找法　Hit@1　Hit@3　Hit@5　MRR（方括號＝題目重抽的 95% 區間）　每題秒數"]
    for m, v in o["methods"].items():
        L.append(f"{name[m]}　" + "　".join(f"{v[k]:.3f} [{v['ci'][k][0]:.3f}, {v['ci'][k][1]:.3f}]" for k in KINDS) + f"　{v['sec_per_question']:.2f}")
    L += ["", "== 與 bge-m3 的差（同一批重抽的題目）=="]
    for m, v in o["methods"].items():
        if m == "bge-m3":
            continue
        for k, lab in (("hit@3", "Hit@3"), ("mrr", "MRR")):
            d = v["diff_vs_bge_m3"][k]
            L.append(f"{name[m]} 減 bge-m3 的 {lab}：{d['diff']:+.3f}，95% 區間 [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]。{verdict(tuple(d['ci']))}。")
        L.append(f"　名次變前 {len(v['better'])} 題（{'、'.join(v['better']) or '無'}）；變後 {len(v['worse'])} 題（{'、'.join(v['worse']) or '無'}）；其餘相同。")
    L += ["", "== 限制 ==",
          "題目由 GPT 單一模型出、金標未經人工確認；題數少，區間寬。每題秒數是這台電腦單次量測，網站同時在跑，只能當量級。"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()

"""票 41：對獨立測試題（票 39 的答案）跑 RAGAS。三個階段，各自可中斷續跑：
  contexts  向主服務 /api/search 取回當時送進生成的段落，與票 39 的出處逐筆比對，一致才沿用舊答案（不呼叫 DeepSeek）；寫 eval/results_heldout_answers_v2.json
  score     用 .venv-ragas 對每題評分（DeepSeek 評審），每題寫完就存 dist/logs/ragas_heldout_progress.json；--metrics 可只跑 faithfulness
  report    讀進度檔，寫 eval/results_heldout_generation.txt／.json
python -X utf8 eval/run_heldout_ragas.py contexts|score|report"""
import argparse
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SRC, V2 = ROOT / "eval/results_heldout_answers.json", ROOT / "eval/results_heldout_answers_v2.json"
PROG = ROOT / "dist/logs/ragas_heldout_progress.json"
OUT = ROOT / "eval/results_heldout_generation"
NOT_FOUND = "查無"
METRICS = ("faithfulness", "answer_relevancy")
# 低於 0.9 的題原因：人工讀答案與段落後寫（RAGAS 沒有輸出逐句判定，原因是推論，不是評審的原話）
REASONS = {
    "h23": "跨公司 8 家。神通一行寫「公司自述的產品沒有寫 AI Agent」，但段落 [2] 的【自述】就列了 MiTAC Agent Builder，這句與段落相反；"
           "其餘多行是「資料中沒有提到」這類沒有出處可對的否定句，評審難以認定有依據。其他正面陳述（凱基、叡揚、藍新）在段落找得到。",
    "h24": "跨公司 8 家，答案 8 行裡有 6 行是「資料沒寫」；這類否定句沒有段落可對，評審多半判無依據，分數被拉低。正面陳述（聯合報、神通）在段落 [1][2][5] 找得到。",
    "h25": "跨公司 8 家，答案 8 行裡有 4 行是「資料沒寫」（神通、台灣大哥大、藍新、聯合報），同樣沒有段落可對。凱基、叡揚、中華網龍、華電的 C# 陳述在段落找得到（華電那行結尾是段落被截斷的「Web A…」）。",
}


def _get(base, path, **q):
    with urllib.request.urlopen(f"{base}{path}?{urllib.parse.urlencode(q)}", timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def _srcs(hits):  # 與 job_rag.answer.answer 相同的去重
    out = []
    for h in hits:
        s = {"company": h["company"], "title": h["heading_path"]}
        if s not in out:
            out.append(s)
    return out


def contexts(a):
    from job_rag.answer import format_source
    old = json.loads(SRC.read_text(encoding="utf-8"))
    rows = []
    for r in old["rows"]:
        r = dict(r, contexts=None, hits=None, context_check=None)
        if r["answer_status"] == "ok":
            time.sleep(1)
            s = _get(a.base, "/api/search", q=r["question"], company=r["detected_company"] or "")
            hits = s.get("hits", [])
            same = s.get("status") == "ok" and _srcs(hits) == r["sources"]
            r["context_check"] = "出處與票 39 一致" if same else "出處與票 39 不一致，不評分"
            if same:
                r["hits"] = [{k: h[k] for k in ("company", "file", "heading_path", "text")} for h in hits]
                r["contexts"] = [format_source(i, h) for i, h in enumerate(hits, 1)]
        rows.append(r)
    V2.write_text(json.dumps({"note": old["note"] + " 答案沿用票 39（未重新生成）；contexts 由 /api/search 重取並與票 39 出處比對。",
                              "deepseek_calls": 0, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: sum(r["context_check"] == k for r in rows) for k in {r["context_check"] for r in rows}})


def _todo(r):
    return r["answerable"] and r["answer_status"] == "ok" and r["answer"].strip() != NOT_FOUND and r["contexts"]


def score(a):
    from job_rag.ragas_judge import make_scorer
    want = tuple(a.metrics.split(","))
    prog = json.loads(PROG.read_text(encoding="utf-8")) if PROG.exists() else {"scored_question_runs": 0, "rows": {}}
    PROG.parent.mkdir(parents=True, exist_ok=True)
    for r in json.loads(V2.read_text(encoding="utf-8"))["rows"]:
        if not _todo(r):
            continue
        cur = prog["rows"].setdefault(r["id"], {})
        need = tuple(m for m in want if not isinstance(cur.get(m), (int, float)))
        if not need:
            continue
        try:
            cur.update(make_scorer(metrics=need)(r["question"], r["answer"], r["contexts"]))
            cur.pop("error", None)
        except Exception as e:  # 失敗就記錄，不補分
            cur["error"] = f"{type(e).__name__}: {e}"[:300]
        prog["scored_question_runs"] += 1  # 每次約 2 次（faithfulness）＋3 次（answer_relevancy）DeepSeek 呼叫，ragas 內部另有重試
        PROG.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
        print(r["id"], cur, flush=True)


def _boot(xs, n=2000, seed=0):
    rng = random.Random(seed)
    m = sorted(sum(rng.choices(xs, k=len(xs))) / len(xs) for _ in range(n))
    return m[int(n * 0.025)], m[int(n * 0.975) - 1]


def report(a):
    rows = json.loads(V2.read_text(encoding="utf-8"))["rows"]
    prog = json.loads(PROG.read_text(encoding="utf-8"))["rows"] if PROG.exists() else {}
    ans = [r for r in rows if r["answerable"]]
    gated = [r["id"] for r in ans if r["answer_status"] == "skipped_low"]
    nf = [r["id"] for r in ans if r["answer_status"] == "ok" and r["answer"].strip() == NOT_FOUND]
    mism = [r["id"] for r in ans if r["answer_status"] == "ok" and r["answer"].strip() != NOT_FOUND and not r["contexts"]]
    todo = [r for r in ans if _todo(r)]
    per = []
    for r in todo:
        p = prog.get(r["id"], {})
        per.append({"id": r["id"], "question": r["question"], "company": r["company"], "answer": r["answer"],
                    "faithfulness": p.get("faithfulness"), "answer_relevancy": p.get("answer_relevancy"), "error": p.get("error")})
    stat = {}
    for m in METRICS:
        xs = [i[m] for i in per if isinstance(i[m], (int, float))]
        stat[m] = {"n": len(xs), "mean": sum(xs) / len(xs) if xs else None, "ci95": _boot(xs) if len(xs) > 1 else None}
    low = [i for i in per if any(isinstance(i[m], (int, float)) and i[m] < 0.9 for m in METRICS)]
    out = {"n_answerable": len(ans), "n_scored_candidates": len(todo), "gated": gated, "model_not_found": nf, "context_mismatch": mism,
           "unanswerable_given_answer": [r["id"] for r in rows if not r["answerable"] and r["answer_status"] == "ok" and r["answer"].strip() != NOT_FOUND],
           "stats": stat, "per_question": per, "low_ids": [i["id"] for i in low],
           "reasons": {i["id"]: REASONS.get(i["id"]) for i in low},
           "note": "答案相關性沒量：本機 bge-m3 嵌入模型要約 5GB 記憶體，當時可用記憶體只有約 5–7GB（主服務與其他子代理各載一個），為避免當機只量忠實度。評審與生成同為 DeepSeek，可能偏樂觀；題數少，只能當方向。答案沿用票 39（K=5、補公司名、已指定公司門檻 0.62）。"}
    OUT.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    f = lambda x: "-" if x is None else f"{x:.3f}"
    L = ["獨立測試題 RAGAS（現行設定：K=5、補公司名、已指定公司門檻 0.62；題組 eval/questions_heldout.json）",
         f"可回答題 {len(ans)} 題：送評 {len(todo)} 題；被查無門檻擋住 {len(gated)} 題（{'、'.join(gated)}）；"
         f"生成回查無 {len(nf)} 題（{'、'.join(nf) or '無'}）；段落重取對不上 {len(mism)} 題。",
         "", f"{'題號':<6}{'忠實度':>8}{'答案相關性':>10}  備註"]
    L += [f"{i['id']:<6}{f(i['faithfulness']):>8}{f(i['answer_relevancy']):>10}  {i['error'] or ''}" for i in per]
    for m, nm in (("faithfulness", "忠實度"), ("answer_relevancy", "答案相關性")):
        s = stat[m]
        L.append(f"{nm}：平均 {f(s['mean'])}（{s['n']} 題）" + (f"；bootstrap 95% 區間 {s['ci95'][0]:.3f}–{s['ci95'][1]:.3f}" if s["ci95"] else ""))
    L += ["", "## 低於 0.9 的題與原因（人工讀答案與段落後寫，是推論）"] + [f"{i['id']}（忠實度 {f(i['faithfulness'])}）：{REASONS.get(i['id'], '（尚未人工檢視）')}" for i in low]
    L += ["", "## 限制", out["note"]]
    OUT.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["contexts", "score", "report"])
    ap.add_argument("--base", default="http://127.0.0.1:5000")
    ap.add_argument("--metrics", default=",".join(METRICS))
    a = ap.parse_args()
    {"contexts": contexts, "score": score, "report": report}[a.phase](a)

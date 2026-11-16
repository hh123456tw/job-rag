"""票 39：獨立測試題 40 題（eval/questions_heldout.json）的檢索評估：python -X utf8 eval/run_heldout.py
只量不調：用目前網站設定（K、已指定公司門檻 NOT_FOUND_THRESHOLD - SCOPED_DROP、補公司名、跨公司路徑），不改任何常數、不呼叫 LLM。
需要 JOB_RAG_CORPUS、JOB_RAG_MODELS。一次只載一個 bge-m3。分流與評分沿用 eval/run_real.py。
寫入 eval/results_heldout.txt 與 eval/results_heldout.json。"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
import run_real  # noqa: E402
from job_rag import retrieval  # noqa: E402
from job_rag.evaluate import DEPTH, evaluate, questions_digest  # noqa: E402
from job_rag.stats import metric_interval  # noqa: E402

QFILE = ROOT / "eval" / "questions_heldout.json"


def main():
    qs = json.loads(QFILE.read_bytes().decode("utf-8"))["questions"]
    routes = {q["id"]: run_real.route(q) for q in qs}
    cross_qs = [q for q in qs if routes[q["id"]] == "跨公司"]
    plain = [q for q in qs if routes[q["id"]] != "跨公司"]
    ans = {q["id"] for q in plain if q["answerable"]}
    st = run_real.SETTINGS
    rep = evaluate(plain, method="bge-m3", detect=st["detect"], dedupe=st["dedupe"])["scores"]
    top, ranks = rep["gate_scores"], rep["ranks"]
    T, TS = retrieval.NOT_FOUND_THRESHOLD, round(retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP, 3)
    rl = list(ranks.values())
    ci = {k: list(metric_interval(rl, k)) for k in ("hit@1", "hit@3", "hit@5", "mrr")}
    gt = rep["gate"]
    cross = run_real.cross_rows(cross_qs)
    out = {"date": datetime.date.today().isoformat(), "digest": questions_digest(qs), "n": len(qs), "n_plain": len(plain),
           "n_cross": len(cross_qs), "settings": st, "k": retrieval.DEFAULT_K, "depth": DEPTH, "threshold": T, "scoped_threshold": TS,
           "cross_floor": retrieval.CROSS_FLOOR, "per_company": retrieval.PER_COMPANY,
           "metrics": rep["metrics"], "ci": ci, "ranks": ranks, "scores": top, "routes": routes,
           "n_answerable": len(ans), "n_unanswerable": len(plain) - len(ans),
           "gate_current": {"blocked_u": gt["unanswerable_blocked"], "passed_u": gt["unanswerable_passed"],
                            "blocked_a": gt["answerable_blocked"]},
           "cross": cross}
    # 沒答案題（含跨公司路徑）的檢索門檻擋住數：跨公司題「狀態 low」＝擋住
    un_cross = [r for r in cross if not r["answerable"]]
    out["unanswerable_total"] = out["n_unanswerable"] + len(un_cross)
    out["unanswerable_blocked_total"] = len(gt["unanswerable_blocked"]) + sum(r["status"] == "low" for r in un_cross)
    (ROOT / "eval/results_heldout.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = render(qs, out)
    (ROOT / "eval/results_heldout.txt").write_text(text, encoding="utf-8")
    print(text)


def _ids(x):
    return "、".join(x) or "無"


def render(qs, o):
    by = {q["id"]: q for q in qs}
    ans = {i for i, q in by.items() if q["answerable"]}
    top, ranks, routes = o["scores"], o["ranks"], o["routes"]
    n_a, n_u = o["n_answerable"], o["n_unanswerable"]
    L = [f"獨立測試題 40 題的檢索評估（票 39）。題檔 eval/questions_heldout.json（{o['n']} 題；摘要 {o['digest'][:16]}）；量測日期 {o['date']}。",
         "這 40 題在跑任何評估之前寫定，沒有用來挑門檻、取段數或任何常數；只量不調，結果差就照實寫。",
         f"量測設定：公司名自動偵測 開、結果去重 開（網站預設）；每題取前 K={o['k']} 段；名次最多看到 {o['depth']}；檢索方式 bge-m3。",
         f"門檻常數（讀自程式，沒有調整）：未指定公司 {o['threshold']:.3f}；已指定公司 {o['scoped_threshold']:.3f}；跨公司 CROSS_FLOOR = {o['cross_floor']}。", ""]
    m, ci = o["metrics"], o["ci"]
    cell = lambda k, lab: f"{lab} {m[k]:.3f} [{ci[k][0]:.3f}, {ci[k][1]:.3f}]"
    L += [f"== 非跨公司題（可回答 {n_a} 題、不可回答 {n_u} 題）==",
          "　".join([cell("hit@1", "Hit@1"), cell("hit@3", "Hit@3"), cell("hit@5", "Hit@5"), cell("mrr", "MRR")]),
          "（方括號＝題目重抽的 95% 區間；題數少，區間很寬。）", "", "題號 分流 名次 最高分 問句"]
    for i in top:
        q = by[i]
        r = "不可回答" if i not in ans else (f"第 {ranks[i]} 名" if ranks[i] else f"前 {o['depth']} 名內沒有")
        who = f"[{q['company']}] " if q.get("company") else ""
        L.append(f"{i} {routes[i]} {r} {top[i]:.3f} {who}{q['question']}")
    L += ["", "== 分數分布 =="]
    a_ids = [i for i in top if i in ans]
    u_ids = [i for i in top if i not in ans]
    amin_i, umax_i = min(a_ids, key=top.get), max(u_ids, key=top.get)
    L.append(f"可回答題最低分 {top[amin_i]:.3f}（{amin_i}）；不可回答題最高分 {top[umax_i]:.3f}（{umax_i}）。"
             + ("兩組分得開。" if top[amin_i] > top[umax_i] else "兩組有重疊，沒有任何單一門檻能全部分開。"))
    c = o["gate_current"]
    L.append(f"現在的設定（已指定公司 {o['scoped_threshold']:.2f}、其餘 {o['threshold']:.2f}）：不可回答題擋住 {len(c['blocked_u'])}/{n_u}"
             f"（{_ids(c['blocked_u'])}），沒擋住 {_ids(c['passed_u'])}；可回答題誤擋 {len(c['blocked_a'])}/{n_a}（{_ids(c['blocked_a'])}）")
    L += ["", f"== 跨公司題（{o['n_cross']} 題；門檻 CROSS_FLOOR = {o['cross_floor']}；每家取 {o['per_company']} 段）==",
          "題號 通過 狀態 相關家數 含關鍵字家數 最高分 問句"]
    for r in o["cross"]:
        L.append(f"{r['id']} {'是' if r['pass'] else '否'} {r['status']} {r['n_relevant']} {r['n_correct']} {r['top']:.3f} {by[r['id']]['question']}")
    L.append(f"通過 {sum(r['pass'] for r in o['cross'])}/{len(o['cross'])}（通過＝可回答題狀態 ok 且至少一家相關公司的段落含關鍵字；不可回答題＝狀態 low；"
             "相關公司由程式做關鍵字比對）")
    L += ["", "== 合計 ==",
          f"沒答案題（15 題，含跨公司路徑）檢索門檻擋住 {o['unanswerable_blocked_total']}/{o['unanswerable_total']}。"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()

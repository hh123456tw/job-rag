"""票 33：新 20 題（eval/questions_real.json）的檢索評估：python -X utf8 eval/run_real.py
需要 JOB_RAG_CORPUS、JOB_RAG_MODELS。不呼叫任何 LLM，不改任何門檻或常數。一次只載 bge-m3。
設定與網站預設一致：公司名自動偵測開、去重開、每題取前 K 段。
- 問句只提到一家公司，或題目有 company（公司頁內提問）：已指定公司，門檻用 NOT_FOUND_THRESHOLD - SCOPED_DROP。
- 沒指定公司、含跨公司詞：走跨公司（每家 PER_COMPANY 段，門檻 CROSS_FLOOR），評分方式同 run_cross.py。
- 其餘：未指定公司，門檻 NOT_FOUND_THRESHOLD。
另外把「可回答題最低分、不可回答題最高分」對 0.70 與 0.62 兩種門檻各算一次擋住／誤擋。
寫入 eval/results_real.txt 與 eval/results_real.json。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402
from job_rag import retrieval  # noqa: E402
from job_rag.evaluate import DEPTH, evaluate, questions_digest  # noqa: E402
from job_rag.stats import metric_interval  # noqa: E402

QFILE = ROOT / "eval" / "questions_real.json"
SETTINGS = {"detect": True, "dedupe": True}


def has(text, kws):
    return any(k.lower() in text.lower() for k in kws)


def route(q):
    """與網站相同的分流：公司頁內提問；否則不是剛好提到一家公司（沒提，或提到兩家以上）→ 跨公司；剛好一家 → 偵測到公司。"""
    if q.get("company"):
        return "公司頁內提問"
    if retrieval.is_cross(q["question"]):
        return "跨公司"
    return "偵測到公司" if retrieval.detect_company(q["question"]) else "未指定公司"


def cross_rows(qs):
    live = {n for _, n in app._company_buttons()}
    segs = [s for s in retrieval._public(retrieval._root(None, "demo")) if s["company"] in live]
    rows = []
    for q in qs:
        kws = q.get("keywords") or q.get("absence_keywords")
        hits = app._cross_hits(q["question"], "demo")
        top = hits[0].get("top", max(h["score"] for h in hits))  # 查無判斷用的 bge-m3 最高分
        low = app._low_cross(hits)
        rel = sorted({s["company"] for s in segs if has(s["text"], kws)})
        got = sorted({h["company"] for h in hits if has(h["text"], kws)} & set(rel))
        ok = (not low and bool(got)) if q["answerable"] else low
        rows.append({"id": q["id"], "answerable": q["answerable"], "top": top, "status": "low" if low else "ok",
                     "n_relevant": len(rel), "n_correct": len(got), "pass": ok, "n_hits": len(hits)})
    return rows


def blocked(scores, ans, t):
    """scores: 題號 -> 最高分；t: 門檻（嚴格小於才擋）。回 {擋住的不可回答題, 沒擋住的不可回答題, 誤擋的可回答題}。"""
    return {"blocked_u": [i for i in scores if i not in ans and scores[i] < t],
            "passed_u": [i for i in scores if i not in ans and scores[i] >= t],
            "blocked_a": [i for i in scores if i in ans and scores[i] < t]}


def main():
    raw = QFILE.read_bytes()
    qs = json.loads(raw.decode("utf-8"))["questions"]
    routes = {q["id"]: route(q) for q in qs}
    cross_qs = [q for q in qs if routes[q["id"]] == "跨公司"]
    plain = [q for q in qs if routes[q["id"]] != "跨公司"]
    ans = {q["id"] for q in plain if q["answerable"]}
    rep = evaluate(plain, method="bge-m3", detect=SETTINGS["detect"], dedupe=SETTINGS["dedupe"])["scores"]
    top, ranks = rep["gate_scores"], rep["ranks"]
    T, TS = retrieval.NOT_FOUND_THRESHOLD, round(retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP, 3)
    rl = list(ranks.values())
    ci = {k: list(metric_interval(rl, k)) for k in ("hit@1", "hit@3", "hit@5", "mrr")}
    gt = rep["gate"]  # 現在的設定：已指定公司 0.62、其餘 0.70
    out = {"digest": questions_digest(qs), "n": len(qs), "n_plain": len(plain), "n_cross": len(cross_qs), "settings": SETTINGS,
           "k": retrieval.DEFAULT_K, "depth": DEPTH, "threshold": T, "scoped_threshold": TS, "cross_floor": retrieval.CROSS_FLOOR,
           "per_company": retrieval.PER_COMPANY,
           "metrics": rep["metrics"], "ci": ci, "ranks": ranks, "scores": top, "routes": routes,
           "n_answerable": len(ans), "n_unanswerable": len(plain) - len(ans),
           "gate_by_threshold": {"0.70": blocked(top, ans, T) | {"t": T}, "0.62": blocked(top, ans, TS) | {"t": TS}},
           "gate_current": {"blocked_u": gt["unanswerable_blocked"], "passed_u": gt["unanswerable_passed"],
                            "blocked_a": gt["answerable_blocked"]},
           "cross": cross_rows(cross_qs)}
    (ROOT / "eval/results_real.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = render(qs, out)
    (ROOT / "eval/results_real.txt").write_text(text, encoding="utf-8")
    print(text)


def _ids(x):
    return "、".join(x) or "無"


def render(qs, o):
    by = {q["id"]: q for q in qs}
    ans = {i for i, q in by.items() if q["answerable"]}
    top, ranks, routes = o["scores"], o["ranks"], o["routes"]
    n_a, n_u = o["n_answerable"], o["n_unanswerable"]
    L = [f"新 20 題真實問法的檢索評估（票 33）。題檔 eval/questions_real.json（{o['n']} 題；摘要 {o['digest'][:16]}）。",
         f"量測設定：公司名自動偵測 開、結果去重 開（網站預設）；每題取前 K={o['k']} 段；名次最多看到 {o['depth']}；檢索方式 bge-m3。",
         f"門檻常數（讀自程式，沒有調整）：未指定公司 NOT_FOUND_THRESHOLD = {o['threshold']:.3f}；已指定公司 {o['scoped_threshold']:.3f}"
         f"（= NOT_FOUND_THRESHOLD - SCOPED_DROP）；跨公司 CROSS_FLOOR = {o['cross_floor']}。",
         f"分流：公司頁內提問或問句只提到一家公司＝已指定公司；沒指定公司且含跨公司詞＝跨公司（{o['n_cross']} 題，另列）；其餘＝未指定公司。",
         "題目是 AI 依本 session 實測踩到的問法擬的，金標只指向公開事實段落，核對狀態都是「待使用者確認」。同一人出題，題數少。", ""]
    m, ci = o["metrics"], o["ci"]
    cell = lambda k, lab: f"{lab} {m[k]:.3f} [{ci[k][0]:.3f}, {ci[k][1]:.3f}]"
    L += [f"== 非跨公司題（可回答 {n_a} 題、不可回答 {n_u} 題）==",
          "　".join([cell("hit@1", "Hit@1"), cell("hit@3", "Hit@3"), cell("hit@5", "Hit@5"), cell("mrr", "MRR")]),
          "（方括號＝題目重抽的 95% 區間；題數這麼少，區間很寬。）", "",
          "題號 分流 名次 最高分 問句"]
    for i in top:
        q = by[i]
        r = "不可回答" if i not in ans else (f"第 {ranks[i]} 名" if ranks[i] else f"前 {o['depth']} 名內沒有")
        who = f"[{q['company']}] " if q.get("company") else ""
        L.append(f"{i} {routes[i]} {r} {top[i]:.3f} {who}{q['question']}")
    L += ["", "== 分數分布與兩種門檻 =="]
    a_ids = [i for i in top if i in ans]
    u_ids = [i for i in top if i not in ans]
    amin_i, umax_i = min(a_ids, key=top.get), max(u_ids, key=top.get)
    L.append(f"可回答題最低分 {top[amin_i]:.3f}（{amin_i}）；不可回答題最高分 {top[umax_i]:.3f}（{umax_i}）。"
             + ("兩組分得開。" if top[amin_i] > top[umax_i] else "兩組有重疊，沒有任何單一門檻能全部分開。"))
    for name, g in o["gate_by_threshold"].items():
        L.append(f"門檻 {name} 套在全部非跨公司題：不可回答題擋住 {len(g['blocked_u'])}/{n_u}（{_ids(g['blocked_u'])}），"
                 f"沒擋住 {_ids(g['passed_u'])}；可回答題誤擋 {len(g['blocked_a'])}/{n_a}（{_ids(g['blocked_a'])}）")
    c = o["gate_current"]
    L.append(f"現在的設定（已指定公司 {o['scoped_threshold']:.2f}、其餘 {o['threshold']:.2f}）：不可回答題擋住 {len(c['blocked_u'])}/{n_u}"
             f"（{_ids(c['blocked_u'])}），沒擋住 {_ids(c['passed_u'])}；可回答題誤擋 {len(c['blocked_a'])}/{n_a}（{_ids(c['blocked_a'])}）")
    sc = [i for i in top if routes[i] != "未指定公司"]
    for lab, ids in (("已指定公司的題", sc), ("未指定公司的題", [i for i in top if i not in sc])):
        a = [top[i] for i in ids if i in ans]
        u = [top[i] for i in ids if i not in ans]
        L.append(f"  {lab}：可回答 {len(a)} 題" + (f"，最低 {min(a):.3f}" if a else "")
                 + f"；不可回答 {len(u)} 題" + (f"，最高 {max(u):.3f}" if u else ""))
    L += ["", f"== 跨公司題（{o['n_cross']} 題；門檻 CROSS_FLOOR = {o['cross_floor']}；每家取 {o['per_company']} 段）==",
          "題號 通過 狀態 相關家數 含關鍵字家數 最高分 問句"]
    for r in o["cross"]:
        L.append(f"{r['id']} {'是' if r['pass'] else '否'} {r['status']} {r['n_relevant']} {r['n_correct']} {r['top']:.3f} {by[r['id']]['question']}")
    L.append(f"通過 {sum(r['pass'] for r in o['cross'])}/{len(o['cross'])}（通過＝可回答題狀態 ok 且至少一家相關公司的段落含關鍵字；不可回答題＝狀態 low；"
             "相關公司由程式做關鍵字比對，不是人工逐段標註）")
    L += ["", "== 是否值得調門檻 ==",
          f"證據強度：弱。非跨公司題只有可回答 {n_a} 題、不可回答 {n_u} 題；同一人出題；擬題時已知 eval/results_scoped.txt 的分數範圍；金標、關鍵字都未經使用者確認。"
          "這份曲線只能說明「分數落在哪裡」，不足以支持調門檻，所以本票沒有動任何門檻常數。要調，需要更多題、其他人出的題，並獨立於挑門檻的題組。"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()

"""專案說明頁的資料層：只讀既有評估輸出檔，不重算、不呼叫外部 API。
檔缺、解析失敗、或和現在的題組對不上（輸出檔過期），一律丟 AboutDataError，不回舊數字或預設值。"""
import json
import re
from pathlib import Path

from . import METHODS
from .evaluate import questions_digest
from .evalset import questions_path
from .generation import FAILED, GATED, SCORED, summarize
from .stats import paired_diff_interval

ROOT = Path(__file__).parent.parent
FOUND = 3  # Hit@3：前 3 名內有金標段落才算找到
CONSISTENT = 0.05  # GPT 複查與 RAGAS 的忠實度平均差在這個範圍內，才說「一致」


RUN1 = "eval/results_generation_run1_judge_without_company.json"  # 第一次 RAGAS 執行（舊題組，評審沒看到公司名）


class AboutDataError(RuntimeError):
    pass


def _read(root: Path, rel):
    p = Path(root) / rel
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AboutDataError(f"找不到評估輸出檔 {rel}；請先重跑對應的評估。") from None
    except (OSError, ValueError) as e:  # JSONDecodeError 是 ValueError
        raise AboutDataError(f"評估輸出檔 {rel} 讀不了或格式不對：{e}") from e


def _found(r) -> bool:
    return r is not None and r <= FOUND


def _table(methods: dict) -> list[dict]:
    out = []
    for m in METHODS:
        if m not in methods:
            raise AboutDataError(f"results_methods.json 少了檢索方式 {m}；請重跑 evaluate --method all。")
        found = sum(_found(r) for r in methods[m]["ranks"].values())  # 前 3 名找到的題數（整數，不從比例反推）
        out.append({"method": m, "found": found, **{k: methods[m][k] for k in ("hit@1", "hit@3", "hit@5", "mrr", "ci")}})
    return out


def _generation(questions: list[dict], rows: list[dict]) -> dict:
    qs = {q["id"]: q["question"] for q in questions}
    if {r["id"]: r["question"] for r in rows} != qs:
        raise AboutDataError("results_generation.json 和現在的題組對不上（題號或題目不同）；請重跑生成層評估。")
    for r in rows:
        if r["status"] == SCORED and (r["faithfulness"] is None or r["answer_relevancy"] is None):
            raise AboutDataError(f"results_generation.json 的 {r['id']} 標為已評分，卻沒有分數。")
    s = summarize(rows)
    if s["faithfulness"] is None:
        raise AboutDataError("results_generation.json 沒有任何已評分的題，算不出平均。")
    a = s["answerable"]
    return {"scored": a["scored"], "n": a["n"], "gated": len(a["gated"]), "failed": len(a["failed"]),
            "faithfulness": s["faithfulness"], "answer_relevancy": s["answer_relevancy"],
            "scored_ids": {r["id"] for r in rows if r["status"] == SCORED}}


def _cross(rows: list[dict], gen: dict) -> dict:
    bad = [r["id"] for r in rows if r["id"] not in gen["scored_ids"]]
    if not rows or bad:
        raise AboutDataError(f"judge_gpt.json 的題號不在 RAGAS 已評分的題內：{'、'.join(bad) or '（沒有資料）'}")
    claims = [c for r in rows for c in r["claims"]]
    mean = sum(r["faithfulness"] for r in rows) / len(rows)
    return {"n": len(rows), "claims": len(claims), "supported": sum(bool(c["supported"]) for c in claims), "mean": mean,
            "consistent": abs(mean - gen["faithfulness"]) <= CONSISTENT}


def _cases(questions: list[dict], methods: dict, table: list[dict]) -> list[dict]:
    """最多 2 個。規則（不手寫）：
    miss：最好的方式（MRR 最高，同分取表中靠前者）前 3 名找到、但有別的方式沒找到的可回答題；沒找到的方式越多越優先，同數取題號小的。
    blocked：bge-m3 查無門檻誤擋的可回答題；最高分越接近門檻越優先。
    先取各 1 個，不足 2 個再從剩下的補。"""
    by = {q["id"]: q for q in questions}
    best = max(table, key=lambda r: (r["mrr"], -[t["method"] for t in table].index(r["method"])))["method"]
    miss = []
    for qid, r in methods[best]["ranks"].items():
        failed = [m for m in METHODS if not _found(methods[m]["ranks"][qid])]
        if _found(r) and failed:
            miss.append({"kind": "miss", "id": qid, "best": best, "best_rank": r, "failed_methods": failed,
                         "ranks": {m: methods[m]["ranks"][qid] for m in METHODS}})
    miss.sort(key=lambda c: (-len(c["failed_methods"]), c["id"]))
    g = methods["bge-m3"]["gate"]
    scores = methods["bge-m3"]["gate_scores"]
    blocked = [{"kind": "blocked", "id": i, "score": scores[i], "threshold": g.get("thresholds", {}).get(i, g["threshold"]),
                "rank": methods["bge-m3"]["ranks"][i]} for i in g["answerable_blocked"]]
    blocked.sort(key=lambda c: (c["threshold"] - c["score"], c["id"]))
    picked = miss[:1] + blocked[:1]
    picked += (miss[1:] + blocked[1:])[: 2 - len(picked)]
    return [c | {"question": by[c["id"]]["question"], "gold": by[c["id"]]["gold"]} for c in picked]


def _followup(root: Path):
    """追問題迷你評估（票 22）。輸出檔不存在回 None（頁面不顯示）；存在但讀不了或和題組對不上，丟 AboutDataError。"""
    if not (root / "eval/results_followups.json").exists():
        return None
    from .followups import QUESTIONS, digest
    r = _read(root, "eval/results_followups.json")
    qs = _read(root, QUESTIONS)["questions"]
    if r.get("digest") != digest(qs):
        raise AboutDataError("results_followups.json 和現在的追問題組對不上（輸出檔過期）；請重跑 python -X utf8 -m job_rag.followups。")
    try:
        return {"n": r["n"], "plain": r["no_expand"]["found"], "expand": r["expand"]["found"], "expanded": len(r["expanded_ids"])}
    except (KeyError, TypeError) as e:
        raise AboutDataError(f"results_followups.json 格式不對：{e}") from e


def _cross_eval(root: Path):
    """跨公司題評估（票 31）。輸出檔不存在、讀不了、或和題檔對不上（過期）都回 None，頁面就不寫這一行，不用舊數字。"""
    import hashlib
    try:
        r = json.loads((root / "eval/results_cross.json").read_text(encoding="utf-8"))
        raw = (root / "eval/questions_cross.json").read_bytes()
        if r["digest"] != hashlib.sha1(raw).hexdigest()[:16]:
            return None
        rows = r["per"][str(r["per_default"])]
        ans = [x for x in rows if x["answerable"]]
        ok = lambda x: (x["status"] == "ok" and x["n_correct"] > 0) if x["answerable"] else x["status"] == "low"
        cov = lambda rs: [x["coverage"] for x in rs if x["answerable"] and x["coverage"] is not None]
        return {"n": len(rows), "passed": sum(map(ok, rows)),
                "names": sorted({n for v in r.get("relevant", {}).values() for n in v}), "n_companies": r.get("n_companies"),
                "by_per": {int(k): sum(cov(v)) / len(cov(v)) for k, v in r["per"].items() if cov(v)}, "n_answerable": len(ans), "answerable_ok": sum(map(ok, ans)),
                "per": r["per_default"], "floor": r["floor"],
                "coverage": sum(x["coverage"] for x in ans if x["coverage"] is not None) / sum(x["coverage"] is not None for x in ans)}
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


SALARY_Q = "薪水多少？"  # 公司頁內只輸入這句、不含公司名：補上公司名再檢索前後的最高分（票 37 第 6 頁）


def _salary_fix(root: Path):
    """results_scoped.txt 寫的補丁前分數（約 0.60，文字檔）與 results_real.json 的補丁後最高分（同一句問題的第一題）。缺檔、過期、對不上都回 None。"""
    try:
        before = re.search(r"原本分數約 ([\d.]+)", (root / "eval/results_scoped.txt").read_text(encoding="utf-8"))
        r = json.loads((root / "eval/results_real.json").read_text(encoding="utf-8"))
        qs = json.loads((root / "eval/questions_real.json").read_text(encoding="utf-8"))["questions"]
        if not before or r["digest"] != questions_digest(qs):
            return None
        qid = next(q["id"] for q in qs if q["question"] == SALARY_Q and q["id"] in r["scores"])
        return {"q": SALARY_Q, "before": float(before.group(1)), "after": r["scores"][qid]}
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return None


def _real_eval(root: Path):
    """新 20 題真實問法評估（票 33）。輸出檔不存在、讀不了、或和題檔對不上（過期）都回 None，頁面就不寫這一句。"""
    try:
        r = json.loads((root / "eval/results_real.json").read_text(encoding="utf-8"))
        qs = json.loads((root / "eval/questions_real.json").read_text(encoding="utf-8"))["questions"]
        if r["digest"] != questions_digest(qs):
            return None
        c, m = r["gate_current"], r["metrics"]
        return {"n": r["n"], "n_answerable": r["n_answerable"], "n_unanswerable": r["n_unanswerable"],
                "hit1": m["hit@1"], "hit3": m["hit@3"], "hit5": m["hit@5"], "mrr": m["mrr"],
                "blocked_u": len(c["blocked_u"]), "blocked_a": len(c["blocked_a"]),
                "cross_passed": sum(x["pass"] for x in r["cross"]), "cross_n": len(r["cross"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


SWEEP_SETS = (("old30", "eval/questions.json"), ("real20", "eval/questions_real.json"), ("held", "eval/questions_heldout.json"))


def _sweep(root: Path):
    """切段上限掃描（票 40）。輸出檔缺、讀不了、或三份題檔任一份對不上（過期）都回 None，頁面就不寫那一句。"""
    try:
        r = json.loads((root / "eval/results_chunk_sweep.json").read_text(encoding="utf-8"))
        for k, rel in SWEEP_SETS:
            qs = json.loads((root / rel).read_text(encoding="utf-8"))["questions"]
            if r["digests"][k] != questions_digest(qs):
                return None
        pl = r["per_length"]
        hit3 = {int(n): v["pooled"]["metrics"]["hit@3"] for n, v in pl.items()}
        return {"n": next(iter(pl.values()))["pooled"]["n"], "hit3": hit3, "conclusion": str(r["conclusion"]["short"])}
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return None


def _e2e(root: Path):
    """端到端拒答檢查（票 35 追加）：真 DeepSeek、網站實際路徑。檔缺、讀不了、或數字自相矛盾都回 None，頁面就不加那半句。"""
    try:
        r = json.loads((root / "eval/results_endtoend.json").read_text(encoding="utf-8"))
        n, ref, rows = r["n"], r["refused"], r["rows"]
        if n != len(rows) or ref != sum(bool(x["refused"]) for x in rows) or r["by_gate"] + r["by_answer_layer"] != ref:
            return None
        return {"n": n, "refused": ref, "by_gate": r["by_gate"], "by_answer_layer": r["by_answer_layer"], "date": r.get("date", "")}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _heldout(root: Path):
    """獨立測試題 100 題。檢索輸出檔缺、讀不了、或和題檔對不上（過期）回 None；端到端拒答另看答案檔，缺或對不上只少那一項。
    拒答＝被檢索門檻擋下，或答案恰為「查無」（與 results_endtoend.json 同一個算法）。"""
    try:
        r = json.loads((root / "eval/results_heldout.json").read_text(encoding="utf-8"))
        qs = json.loads((root / "eval/questions_heldout.json").read_text(encoding="utf-8"))["questions"]
        if r["digest"] != questions_digest(qs):
            return None
        m, ci = r["metrics"], r["ci"]
        out = {"n": r["n"], "n_plain_answerable": r["n_answerable"], "hit3": m["hit@3"], "hit3_ci": ci["hit@3"], "mrr": m["mrr"], "mrr_ci": ci["mrr"],
               "blocked_u": r["unanswerable_blocked_total"], "n_unanswerable": r["unanswerable_total"], "e2e": None,
               "by_type": r.get("by_type") or {}, "cross_pass": sum(x["pass"] for x in r["cross"] if x["answerable"]),
               "cross_n": sum(x["answerable"] for x in r["cross"])}
        if out["n_unanswerable"] != sum(not q["answerable"] for q in qs):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        rows = {x["id"]: x for x in json.loads((root / "eval/results_heldout_answers.json").read_text(encoding="utf-8"))["rows"]}
        by = {q["id"]: q for q in qs}
        un = [q["id"] for q in qs if not q["answerable"]]
        if set(rows) != set(by) or any(rows[i]["question"] != by[i]["question"] for i in rows):
            return out
        ref = sum(rows[i]["answer_status"] == "skipped_low" or (rows[i]["answer_status"] == "ok" and (rows[i]["answer"] or "").strip() == "查無") for i in un)
        out["e2e"] = {"refused": ref, "n": len(un)}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return out


def _qsets(root: Path):
    """調參用 30 題與調完才測 100 題各題型的題數與一個例題（說明頁「這 130 題問什麼」用）。題檔缺或讀不了回 None。"""
    try:
        out = {}
        for key, rel in (("tune", "eval/questions.json"), ("held", "eval/questions_heldout.json")):
            qs = json.loads((root / rel).read_text(encoding="utf-8"))["questions"]
            kinds = {}
            for q in qs:
                k = kinds.setdefault(q["type"], {"n": 0, "example": q["question"]})
                k["n"] += 1
            out[key] = {"n": len(qs), "kinds": kinds}
        return out
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _mrr_diff(methods: dict) -> dict:
    """bge-m3 減混合的 MRR 差與 95% 區間（同一批重抽的題目，算法與 evaluate 的 results_methods.txt 相同）。"""
    a, b = methods["bge-m3"], methods["hybrid"]
    ids = list(a["ranks"])
    if set(ids) != set(b["ranks"]):
        raise AboutDataError("results_methods.json 的 bge-m3 與混合題號對不上；請重跑 evaluate --method all。")
    lo, hi = paired_diff_interval([a["ranks"][i] for i in ids], [b["ranks"][i] for i in ids])
    return {"diff": a["mrr"] - b["mrr"], "lo": lo, "hi": hi}


def _mrr_diffs(methods: dict) -> list[dict]:
    """bge-m3 減其他四種找法的 MRR 差與 95% 區間（同 _mrr_diff 的算法，森林圖用）。"""
    a = methods["bge-m3"]["ranks"]
    ids = list(a)
    out = []
    for m in METHODS:
        if m == "bge-m3":
            continue
        b = methods[m]["ranks"]
        lo, hi = paired_diff_interval([a[i] for i in ids], [b[i] for i in ids])
        out.append({"method": m, "diff": methods["bge-m3"]["mrr"] - methods[m]["mrr"], "lo": lo, "hi": hi})
    return out


def _versus(methods: dict) -> list[dict]:
    """bge-m3 對其他四種找法逐題比：以 1/名次（前 10 名內沒有算 0）判誰排得比較前。win＝bge-m3 比較前，loss＝對方比較前。"""
    a = methods["bge-m3"]["ranks"]
    rr = lambda r: 1 / r if r else 0.0
    out = []
    for m in METHODS:
        if m == "bge-m3":
            continue
        b = methods[m]["ranks"]
        w = sum(rr(a[i]) > rr(b[i]) for i in a)
        l = sum(rr(a[i]) < rr(b[i]) for i in a)
        out.append({"method": m, "win": w, "tie": len(a) - w - l, "loss": l, "n": len(a)})
    return out


def _perf(root: Path):
    """bge-m3 載入與查詢時間：只引用 eval/spaces_feasibility.md（本機模擬，較快的那組核心）。檔缺或格式對不上就回 None，不猜。"""
    try:
        t = (root / "eval/spaces_feasibility.md").read_text(encoding="utf-8")
    except OSError:
        return None
    load = re.search(r"\|\s*載入 bge-m3\s*\|\s*([\d.]+) 秒", t)
    query = re.search(r"\|\s*預熱後單次查詢，bge-m3，中位數（\d+ 次）\s*\|\s*([\d.]+) 秒", t)
    return {"load": load.group(1), "query": query.group(1)} if load and query else None


def _ragas_fix(root: Path, gen):
    """第一次 RAGAS（舊題組、評審沒看到公司名）的忠實度。目前的生成層輸出沒有、舊輸出檔缺或讀不了，就回 None（只略過這一項）。"""
    if gen is None:
        return None
    try:
        first = summarize(_read(root, RUN1))
        return {"first": first["faithfulness"], "first_scored": first["answerable"]["scored"],
                "now": gen["faithfulness"], "now_scored": gen["scored"]} if first["faithfulness"] is not None else None
    except (AboutDataError, KeyError, TypeError, ValueError, AttributeError):
        return None


def _held_methods(root: Path):
    """獨立題上 hybrid 與 reranker 對 bge-m3 的比較（票 43、44）。輸出檔缺或讀不了回 None（頁面維持「沒量過」）。"""
    try:
        r = json.loads((root / "eval/results_heldout_methods.json").read_text(encoding="utf-8"))
        b = r["methods"]["bge-m3"]
        out = {"n": r["n"], "cand": r["cand"], "reranker": r["reranker"], "base_mrr": b["mrr"], "base_hit1": b["hit@1"],
               "not_first": sum(x != 1 for x in r["ranks"]["bge-m3"].values())}
        for m in ("hybrid", "rerank"):
            v = r["methods"][m]
            d = v["diff_vs_bge_m3"]["mrr"]
            out[m] = {"mrr": v["mrr"], "diff": d["diff"], "lo": d["ci"][0], "hi": d["ci"][1], "sec": v["sec_per_question"],
                      "better": len(v["better"]), "worse": len(v["worse"])}
        return out
    except (OSError, KeyError, TypeError, ValueError):
        return None


def _heldout_gen(root: Path):
    """獨立題 RAGAS（票 41，現行設定）。輸出檔缺、讀不了、或沒有任何有效忠實度回 None；答案相關性沒量就是 None。"""
    try:
        r = json.loads((root / "eval/results_heldout_generation.json").read_text(encoding="utf-8"))
        f, a = r["stats"]["faithfulness"], r["stats"]["answer_relevancy"]
        if not f["n"] or not isinstance(f["mean"], (int, float)):
            return None
        return {"n": f["n"], "faithfulness": f["mean"], "ci": f["ci95"],
                "answer_relevancy": a["mean"] if a["n"] and isinstance(a["mean"], (int, float)) else None, "n_ar": a["n"],
                "gated": len(r["gated"]), "not_found": len(r["model_not_found"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _heldout_cross(root: Path):
    """獨立題的 GPT 複查（judge_gpt_heldout.json）。缺檔、讀不了、或題號不在 RAGAS 已評分的獨立題內回 None（頁面不寫這一句）。"""
    try:
        rows = json.loads((root / "eval/crossjudge/judge_gpt_heldout.json").read_text(encoding="utf-8"))
        ids = {q["id"] for q in json.loads((root / "eval/results_heldout_generation.json").read_text(encoding="utf-8"))["per_question"]}
        if not rows or any(r["id"] not in ids for r in rows):
            return None
        claims = [c for r in rows for c in r["claims"]]
        return {"n": len(rows), "claims": len(claims), "supported": sum(bool(c["supported"]) for c in claims)}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load(root=None) -> dict:
    root = Path(root or ROOT)
    questions = _read(root, questions_path(root))["questions"]
    m = _read(root, "eval/results_methods.json")
    if m.get("digest") != questions_digest(questions):
        raise AboutDataError("results_methods.json 和現在的題組對不上（題組已變動，輸出檔過期）；請重跑 evaluate --method all。")
    table = _table(m["methods"])
    # 公開版沒有 DeepSeek 金鑰就沒有生成層輸出：兩個檔都不存在才略過那一塊；只缺一個或壞掉仍是錯誤
    gen_files = [root / "eval/results_generation.json", root / "eval/crossjudge/judge_gpt.json"]
    if not any(f.exists() for f in gen_files):
        gen = cross = None
    else:
        gen = _generation(questions, _read(root, "eval/results_generation.json"))
        cross = _cross(_read(root, "eval/crossjudge/judge_gpt.json"), gen)
    gate = m["methods"]["bge-m3"].get("gate")
    if not gate:
        raise AboutDataError("results_methods.json 的 bge-m3 沒有查無門檻結果。")
    try:  # 追問評估的錯誤只影響那一小段，不拖垮整頁
        followup, followup_error = _followup(root), ""
    except AboutDataError as e:
        followup, followup_error = None, str(e)
    return {
        "followup": followup, "followup_error": followup_error, "cross_eval": _cross_eval(root), "real_eval": _real_eval(root), "e2e": _e2e(root), "held": _heldout(root), "qsets": _qsets(root), "sweep": _sweep(root), "held_gen": _heldout_gen(root), "held_cross": _heldout_cross(root), "held_methods": _held_methods(root),
        "n_answerable": m["n_answerable"], "n_unanswerable": m["n_unanswerable"],
        "bootstrap": m["bootstrap"], "depth": m["depth"], "table": table,
        "generation": gen and {k: v for k, v in gen.items() if k != "scored_ids"}, "cross": cross,
        "gate": {"threshold": gate["threshold"], "scoped_threshold": gate.get("scoped_threshold"), "n_scoped": len(gate.get("scoped_ids", [])),
                 "unanswerable_blocked": len(gate["unanswerable_blocked"]),
                 "n_unanswerable": m["n_unanswerable"], "answerable_blocked": len(gate["answerable_blocked"]),
                 "n_answerable": m["n_answerable"]},
        "mrr_diff": _mrr_diff(m["methods"]), "mrr_diffs": _mrr_diffs(m["methods"]), "versus": _versus(m["methods"]), "salary_fix": _salary_fix(root), "perf": _perf(root),
        "ragas_fix": _ragas_fix(root, gen), "live_test": (root / "eval/live_test.md").exists(),
        "cases": _cases(questions, m["methods"], table),
    }

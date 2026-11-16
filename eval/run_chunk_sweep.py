"""票 40：切段上限掃描（400／600／900／1200 字）。只量不改：python -X utf8 eval/run_chunk_sweep.py
需要 JOB_RAG_CORPUS、JOB_RAG_MODELS。不呼叫任何 LLM，不改 retrieval.CHUNK／OVERLAP 與任何門檻。一次只載一個 bge-m3。
做法：每個長度各開一個子程序（--chunk N），在子程序內暫時改 CHUNK／OVERLAP（OVERLAP ＝ 上限 × 15% 取整），
快取放在獨立的臨時目錄（--work，預設在系統暫存區），不碰 .cache/。每個長度的中間結果存成 work/chunk_N.json，
中斷後重跑會跳過已完成的長度。三組題（questions.json、questions_real.json、questions_heldout.json）都用目前網站設定
（偵測公司開、去重開、每題 K 段、已指定公司降門檻、跨公司路徑），分流與評分沿用 eval/run_real.py。
全部長度完成後寫入 eval/results_chunk_sweep.txt 與 .json。--report 只重新彙整，不編碼。"""
import argparse
import datetime
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

LENGTHS = (400, 600, 900, 1200)
BASE = 600  # 目前網站用的長度；其他長度都跟它比
RATIO = 0.15
GROUPS = (("old30", "questions.json", "舊 30 題"), ("real20", "questions_real.json", "真實 20 題"), ("held40", "questions_heldout.json", "獨立 40 題"))
OUT = ROOT / "eval" / "results_chunk_sweep"
NO_CUT = 10 ** 9  # 基線：不切段


def overlap_for(n: int) -> int:
    return round(n * RATIO)


def default_work() -> Path:
    return Path(os.environ.get("JOB_RAG_SWEEP_WORK") or Path(tempfile.gettempdir()) / "job_rag_chunk_sweep")


def cache_dir(work, n) -> Path:
    """每個長度自己的向量快取。絕不等於專案的 .cache/（或它底下）。"""
    d = (Path(work) / f"cache_{n}").resolve()
    real = (ROOT / ".cache").resolve()
    if d == real or real in d.parents:
        raise RuntimeError(f"臨時快取不可放在 {real} 之內：{d}")
    return d


@contextmanager
def chunk_size(n: int, overlap: int | None = None):
    """暫時改 retrieval.CHUNK／OVERLAP 並清掉依賴它們的快取；離開（含例外）一定還原。"""
    from job_rag import retrieval as r
    old = r.CHUNK, r.OVERLAP
    clear = lambda: [f.cache_clear() for f in (r._parse, r._public, r._bm25, r._index, r._load_bundle)]
    r.CHUNK, r.OVERLAP = n, overlap_for(n) if overlap is None else overlap
    clear()
    try:
        yield
    finally:
        r.CHUNK, r.OVERLAP = old
        clear()


# ---- 段落統計（估計值：用簡單規則，不是人工逐段檢查）----
URL = re.compile(r"https?://\S+")
ROW = re.compile(r"^[ \t]*\|[^\n]*", re.M)
URL_END = ")）|,，。、；;"  # 緊接在網址後的這些字不算網址的一部分


def boundary_cuts(segs, chunk: int, overlap: int) -> dict:
    """相鄰兩段若來自同一個標題段落（下一段開頭＝上一段尾端的重疊區），檢查切點落在網址或表格列的哪裡。
    end_cut：上一段的結尾切在網址／表格列中間；lost：其中開頭也不在下一段的重疊區內（兩段都不完整）；
    start_mid：下一段的開頭落在網址／表格列中間（上一段還是完整的，只有下一段開頭殘缺）。"""
    step = chunk - overlap
    c = {f"{k}_{x}": 0 for k in ("url", "row") for x in ("end_cut", "lost", "start_mid")} | {"boundaries": 0}
    for p, n in zip(segs, segs[1:]):
        pt, nt = p["text"], n["text"]
        if (p["file"], p["heading_path"]) != (n["file"], n["heading_path"]) or len(pt) != chunk or not nt.startswith(pt[step:]):
            continue
        c["boundaries"] += 1
        nxt = nt[overlap] if len(nt) > overlap else None  # 上一段結尾後面的那個字；沒有＝標題段落剛好在此結束
        for kind, rx in (("url", URL), ("row", ROW)):
            for m in rx.finditer(pt):
                s, e = m.span()
                if e == len(pt) and nxt is not None and (nxt not in URL_END and not nxt.isspace() if kind == "url" else nxt != "\n"):
                    c[f"{kind}_end_cut"] += 1
                    c[f"{kind}_lost"] += s < step
                if s < step < e:
                    c[f"{kind}_start_mid"] += 1
    return c


def length_stats(segs, chunk: int, overlap: int) -> dict:
    lens = [len(s["text"]) for s in segs]
    return {"n_segments": len(lens), "mean": statistics.mean(lens), "median": statistics.median(lens), "max": max(lens),
            "at_cap": sum(x == chunk for x in lens), "top_bin": sum(x > chunk - 100 for x in lens)} | boundary_cuts(segs, chunk, overlap)


def _squash(s):
    return re.sub(r"\s+", "", s).lower()


def _under(s, g):
    h = s["heading_path"]
    return s["file"] == g["file"] and (h == g["heading"] or h.startswith(g["heading"] + " > "))


def gold_intact(golds, segs) -> list[bool]:
    """每個金標：引文是否完整落在金標標題之下的某一段內。"""
    return [any(_squash(g["quote"]) in _squash(s["text"]) for s in segs if _under(s, g)) for g in golds]


def strict_rank(results, golds):
    """命中段必須在金標標題之下，而且含完整金標引文（比平常的命中更嚴）。"""
    for i, r in enumerate(results, 1):
        for g in golds:
            if _squash(g["quote"]) in _squash(r["text"]) and any(_under(loc, g) for loc in [r, *r.get("also_in", [])]):
                return i
    return None


def public_segs():
    from job_rag import retrieval
    return list(retrieval._public(retrieval._root(None, "demo")))


def gold_cross_rows(qs, rr):
    """舊 30 題裡有金標、沒有關鍵字的跨公司題（c01、c06）：通過＝狀態 ok 且跨公司結果有一段在金標標題之下。"""
    rows = []
    for q in qs:
        hits = rr.app._cross_hits(q["question"], "demo")
        low = rr.app._low_cross(hits)
        got = any(_under(h, g) for h in hits for g in q["gold"])
        rows.append({"id": q["id"], "answerable": q["answerable"], "top": max(h["score"] for h in hits), "status": "low" if low else "ok",
                     "pass": (not low and got) if q["answerable"] else low})
    return rows


# ---- 一個長度的完整評估（子程序內執行）----
def run_group(qs, routes, segs, rr):
    from job_rag import detect_company, search
    from job_rag.evaluate import DEPTH, evaluate
    st = rr.SETTINGS
    cross_qs = [q for q in qs if routes[q["id"]] == "跨公司"]
    plain = [q for q in qs if routes[q["id"]] != "跨公司"]
    rep = evaluate(plain, method="bge-m3", detect=st["detect"], dedupe=st["dedupe"])["scores"]
    gt = rep["gate"]
    cross = rr.cross_rows([q for q in cross_qs if q.get("keywords") or q.get("absence_keywords")]) + gold_cross_rows(
        [q for q in cross_qs if not (q.get("keywords") or q.get("absence_keywords"))], rr)
    strict, lat = {}, []
    for q in plain:
        co = q.get("company") or detect_company(q["question"])
        t = time.perf_counter()
        res = search(q["question"], method="bge-m3", company=co, k=DEPTH, gate=False, dedupe=st["dedupe"])
        lat.append((time.perf_counter() - t) * 1000)
        if q["answerable"]:
            strict[q["id"]] = strict_rank(res, q["gold"])
    for q in cross_qs:
        t = time.perf_counter()
        rr.app._cross_hits(q["question"], "demo")
        lat.append((time.perf_counter() - t) * 1000)
    return {"n": len(qs), "n_plain": len(plain), "n_cross": len(cross_qs),
            "n_answerable": sum(q["answerable"] for q in plain), "n_unanswerable": sum(not q["answerable"] for q in plain),
            "ranks": rep["ranks"], "strict_ranks": strict, "routes": routes,
            "gate": {"blocked_u": gt["unanswerable_blocked"], "passed_u": gt["unanswerable_passed"], "blocked_a": gt["answerable_blocked"]},
            "cross": cross, "latency_ms": lat}


def run_one(n: int, work) -> Path:
    from job_rag.evaluate import questions_digest
    if not os.environ.get("JOB_RAG_CORPUS"):
        raise SystemExit("未設定 JOB_RAG_CORPUS")
    os.environ["JOB_RAG_CACHE"] = str(cache_dir(work, n))
    os.environ.pop("JOB_RAG_BUNDLE", None)  # 要用原始語料，與 run_real／run_heldout 相同
    allq = {k: json.loads((ROOT / "eval" / f).read_bytes().decode("utf-8"))["questions"] for k, f, _ in GROUPS}
    with chunk_size(NO_CUT, 0):  # 基線：不切段時金標引文本來就找不找得到（找不到的不算被切斷）
        base = public_segs()
        base_gold = {k: {q["id"]: gold_intact(q["gold"], base) for q in qs if q["answerable"] and q["gold"]} for k, qs in allq.items()}
    with chunk_size(n):
        from job_rag import retrieval
        ov = retrieval.OVERLAP
        import run_real as rr
        segs = public_segs()
        out = {"chunk": n, "overlap": ov, "date": datetime.date.today().isoformat(),
               "segments_sha1": retrieval.segments_hash(s["_index"] for s in segs), "stats": length_stats(segs, n, ov), "groups": {}}
        for k, qs in allq.items():
            routes = {q["id"]: rr.route(q) for q in qs}
            g = run_group(qs, routes, segs, rr)
            g["digest"] = questions_digest(qs)
            g["gold"] = {i: {"base": b, "now": gold_intact(next(q for q in qs if q["id"] == i)["gold"], segs)} for i, b in base_gold[k].items()}
            out["groups"][k] = g
            print(f"[{n}] {k} 完成", flush=True)
    p = Path(work) / f"chunk_{n}.json"
    p.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


# ---- 彙整 ----
def _m(ranks):
    from job_rag.evaluate import metrics
    return metrics(list(ranks)) if ranks else None


def _ci(ranks, k):
    from job_rag.stats import metric_interval
    return list(metric_interval(list(ranks), k)) if ranks else None


def summarize(runs: dict) -> dict:
    """runs: 長度 -> 子程序輸出。回傳 results_chunk_sweep.json 的內容。"""
    from job_rag.stats import paired_metric_interval
    res = {"date": max(r["date"] for r in runs.values()), "lengths": list(runs), "overlap": {n: r["overlap"] for n, r in runs.items()},
           "ratio": RATIO, "settings": {"detect": True, "dedupe": True, "k": 5, "method": "bge-m3"},
           "digests": {k: next(iter(runs.values()))["groups"][k]["digest"] for k, _, _ in GROUPS}, "per_length": {}}
    for n, r in runs.items():
        for k, _, _ in GROUPS:
            assert r["groups"][k]["digest"] == res["digests"][k], f"{n} 長度的 {k} 題檔摘要和別的長度不同：不能混在一起比"
    pooled = {}
    for n, r in runs.items():
        gs, row = r["groups"], {"stats": r["stats"], "segments_sha1": r["segments_sha1"], "groups": {}}
        for k, g in gs.items():
            ranks, strict = list(g["ranks"].values()), list(g["strict_ranks"].values())
            m = _m(ranks)
            un_cross = [x for x in g["cross"] if not x["answerable"]]
            an_cross = [x for x in g["cross"] if x["answerable"]]
            gold = g["gold"].values()
            row["groups"][k] = {
                "n": g["n"], "n_plain": g["n_plain"], "n_cross": g["n_cross"], "n_answerable": g["n_answerable"], "n_unanswerable": g["n_unanswerable"],
                "metrics": m, "ci": {x: _ci(ranks, x) for x in ("hit@1", "hit@3", "hit@5", "mrr")} if m else None,
                "strict_hit3": (sum(x is not None and x <= 3 for x in strict) / len(strict)) if strict else None,
                "blocked_u_plain": len(g["gate"]["blocked_u"]), "blocked_a_plain": len(g["gate"]["blocked_a"]),
                "blocked_u_total": len(g["gate"]["blocked_u"]) + sum(x["status"] == "low" for x in un_cross),
                "n_u_total": g["n_unanswerable"] + len(un_cross),
                "blocked_a_total": len(g["gate"]["blocked_a"]) + sum(x["status"] == "low" for x in an_cross),
                "n_a_total": g["n_answerable"] + len(an_cross),
                "cross_passed": sum(x["pass"] for x in g["cross"]), "cross_n": len(g["cross"]),
                "gold_q": len(g["gold"]),
                "gold_all_cut": sum(any(v["base"]) and not any(v["now"]) for v in gold),
                "gold_any_cut": sum(any(b and not f for b, f in zip(v["base"], v["now"])) for v in gold),
                "gold_items": sum(len(v["now"]) for v in gold),
                "gold_items_cut": sum(b and not f for v in gold for b, f in zip(v["base"], v["now"])),
                "gold_missing_at_baseline": sum(not any(v["base"]) for v in gold),
                "latency_ms": g["latency_ms"]}
        keyed = lambda field: {f"{k}:{i}": x for k, g in gs.items() for i, x in g[field].items()}
        pr = keyed("ranks")
        pooled[n] = pr
        pm, ps = _m(pr.values()), list(keyed("strict_ranks").values())
        lat = [x for g in gs.values() for x in g["latency_ms"]]
        row["pooled"] = {"n": len(pr), "metrics": pm, "ci": {x: _ci(pr.values(), x) for x in ("hit@1", "hit@3", "hit@5", "mrr")},
                         "strict_hit3": sum(x is not None and x <= 3 for x in ps) / len(ps) if ps else None,
                         "blocked_u_total": sum(row["groups"][k]["blocked_u_total"] for k in gs), "n_u_total": sum(row["groups"][k]["n_u_total"] for k in gs),
                         "blocked_a_total": sum(row["groups"][k]["blocked_a_total"] for k in gs), "n_a_total": sum(row["groups"][k]["n_a_total"] for k in gs),
                         "gold_all_cut": sum(row["groups"][k]["gold_all_cut"] for k in gs), "gold_any_cut": sum(row["groups"][k]["gold_any_cut"] for k in gs),
                         "gold_q": sum(row["groups"][k]["gold_q"] for k in gs),
                         "latency_median_ms": statistics.median(lat)}
        res["per_length"][str(n)] = row
    if BASE in runs:  # 與 600 的配對差（同一批題）
        ids = list(pooled[BASE])
        res["paired_vs_base"] = {str(n): {k: {"diff": (_m([pooled[n][i] for i in ids])[k] - _m([pooled[BASE][i] for i in ids])[k]),
                                              "ci": list(paired_metric_interval([pooled[n][i] for i in ids], [pooled[BASE][i] for i in ids], k))}
                                          for k in ("hit@1", "hit@3", "mrr")} for n in runs if n != BASE}
    res["conclusion"] = conclude(res)
    return res


def conclude(res) -> dict:
    """結論句只由輸出檔內的數字推出。回 {"short": 一句話, "overlap": 區間是否重疊, "best_hit3": 點估計最高的長度}。"""
    pl = res["per_length"]
    ci = {n: pl[n]["pooled"]["ci"]["hit@3"] for n in pl}
    pts = {n: pl[n]["pooled"]["metrics"]["hit@3"] for n in pl}
    overlap = all(max(a[0], b[0]) <= min(a[1], b[1]) for a in ci.values() for b in ci.values())
    best = max(pts, key=lambda n: (pts[n], -int(n)))  # 同分取較短
    sig = [(n, k, d) for n, ks in res.get("paired_vs_base", {}).items() for k, d in ks.items() if d["ci"][0] > 0 or d["ci"][1] < 0]
    if not sig:
        short = "差異在區間內：四種長度的 Hit@3 區間互相重疊，與 600 的配對差異區間都含 0，只能當方向，沒有改切段長度"
    else:
        n, k, d = sig[0]
        short = (f"{n} 字與 600 字的 {k} 差 {d['diff']:+.3f}（95% 區間 {d['ci'][0]:+.3f} 到 {d['ci'][1]:+.3f}，不含 0），"
                 "但題少、三組題裡有同一人出的題，只能當方向，沒有改切段長度")
    return {"short": short, "intervals_overlap": overlap, "best_hit3": int(best), "significant": [[int(n), k] for n, k, _ in sig]}


def render(res, qd) -> str:
    pl, ns = res["per_length"], list(res["per_length"])
    cell = lambda v, c=None: f"{v:.3f}" + (f" [{c[0]:.3f}, {c[1]:.3f}]" if c else "")
    L = [f"切段上限掃描（票 40）。量測日期 {res['date']}。只量不改：retrieval.CHUNK／OVERLAP 與 .cache/ 都沒動；每個長度各用獨立臨時快取。",
         f"長度與重疊：" + "、".join(f"{n} 字／重疊 {res['overlap'][n]}" for n in ns) + f"（重疊約 {RATIO:.0%}，取整）。目前網站是 {BASE} 字／90。",
         "量測設定：網站目前設定（公司名自動偵測 開、去重 開、每題取前 K=5 段、bge-m3、已指定公司門檻 0.620／其餘 0.700、跨公司走各家取 2 段、CROSS_FLOOR）。"
         "三組題各自分流（單一公司題／跨公司題），評分沿用 eval/run_real.py。",
         "題檔摘要：" + "；".join(f"{f} {res['digests'][k][:16]}" for k, f, _ in GROUPS), "",
         "證據強度：弱。三組題共 " + f"{pl[ns[0]]['pooled']['n']} 題單一公司有答案題（可回答題少）；舊 30 題曾用來挑門檻、真實 20 題與舊題同一人出、獨立 40 題未用來調參；"
         "同一份語料；金標只指到「檔案＋標題」，不是逐段標註。差異小於區間就只能當方向。", ""]
    L += ["== 一、各長度的段落統計（取自載入後的公開事實段落）==",
          "長度 總段數 平均 中位數 最大 等於上限的段 落在上限格(上限-99~上限)的段 被再切的接縫數"]
    for n in ns:
        s = pl[n]["stats"]
        L.append(f"{n} {s['n_segments']} {s['mean']:.0f} {s['median']:.0f} {s['max']} {s['at_cap']}（{s['at_cap'] / s['n_segments']:.0%}） "
                 f"{s['top_bin']}（{s['top_bin'] / s['n_segments']:.0%}） {s['boundaries']}")
    L += ["", "網址與表格列被切斷（估計：用簡單規則數接縫，不是人工逐段檢查）。接縫＝同一標題段落內相鄰兩段的交界。",
          "段尾切斷＝上一段結尾落在網址／表格列中間；兩段都殘缺＝其中開頭也不在下一段的重疊區內（重疊救不回）；段首殘缺＝下一段開頭落在網址／表格列中間。",
          "長度 網址段尾切斷 網址兩段都殘缺 網址段首殘缺 | 表格列段尾切斷 表格列兩段都殘缺 表格列段首殘缺"]
    for n in ns:
        s = pl[n]["stats"]
        L.append(f"{n} {s['url_end_cut']} {s['url_lost']} {s['url_start_mid']} | {s['row_end_cut']} {s['row_lost']} {s['row_start_mid']}")
    for k, f, name in GROUPS:
        L += ["", f"== 二、{name}（{f}）=="]
        g0 = pl[ns[0]]["groups"][k]
        L.append(f"單一公司題 {g0['n_plain']} 題（有答案 {g0['n_answerable']}、沒答案 {g0['n_unanswerable']}）；跨公司題 {g0['n_cross']} 題。方括號＝題目重抽 95% 區間。")
        L.append("長度 | Hit@1 | Hit@3 | Hit@5 | MRR | 嚴格Hit@3(命中段須含完整引文)")
        for n in ns:
            g = pl[n]["groups"][k]
            m, c = g["metrics"], g["ci"]
            L.append(f"{n} | " + " | ".join(cell(m[x], c[x]) for x in ("hit@1", "hit@3", "hit@5", "mrr")) + f" | {cell(g['strict_hit3'])}")
        L.append("長度 | 沒答案題擋住(含跨公司) | 有答案題誤擋(含跨公司) | 跨公司通過 | 金標被切斷題數(全部金標都找不到完整引文／任一金標被切斷／有金標題數)")
        for n in ns:
            g = pl[n]["groups"][k]
            L.append(f"{n} | {g['blocked_u_total']}/{g['n_u_total']} | {g['blocked_a_total']}/{g['n_a_total']} | {g['cross_passed']}/{g['cross_n']} | "
                     f"{g['gold_all_cut']}／{g['gold_any_cut']}／{g['gold_q']}（金標 {g['gold_items_cut']}/{g['gold_items']} 條被切斷）")
    L += ["", f"== 三、三組合併（單一公司有答案題 {pl[ns[0]]['pooled']['n']} 題；跨公司題不在 Hit／MRR 內）=="]
    L.append("長度 | Hit@1 | Hit@3 | Hit@5 | MRR | 嚴格Hit@3 | 沒答案題擋住 | 有答案題誤擋 | 金標被切斷題數(全部／任一／有金標題數) | 查詢耗時中位數")
    for n in ns:
        p = pl[n]["pooled"]
        m, c = p["metrics"], p["ci"]
        L.append(f"{n} | " + " | ".join(cell(m[x], c[x]) for x in ("hit@1", "hit@3", "hit@5", "mrr")) + f" | {cell(p['strict_hit3'])} | "
                 f"{p['blocked_u_total']}/{p['n_u_total']} | {p['blocked_a_total']}/{p['n_a_total']} | {p['gold_all_cut']}／{p['gold_any_cut']}／{p['gold_q']} | {p['latency_median_ms']:.0f} ms")
    L.append("查詢耗時＝每題一次 search（單一公司題，K=10 名次）或跨公司檢索的牆上時間，含編碼問句；本機同時有其他程序，數字會晃，只能看量級。")
    if "paired_vs_base" in res:
        L += ["", f"與 {BASE} 字的配對差（同一批題，三組合併；括號＝差的 95% 區間）："]
        for n, ks in res["paired_vs_base"].items():
            L.append(f"  {n}：" + "　".join(f"{k} {d['diff']:+.3f} [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]" for k, d in ks.items()))
    c = res["conclusion"]
    L += ["", "== 四、結論 ==", f"Hit@3 的四個 95% 區間{'互相重疊' if c['intervals_overlap'] else '有不重疊的'}；點估計最高的是 {c['best_hit3']} 字（同分取較短）。", c["short"] + "。",
          "沒有改 CHUNK／OVERLAP，也沒有重算既有結果檔。若要採用別的長度，需要重跑全部評估與端到端結果，另開一張票。",
          "金標被切斷題數的算法：金標引文（去空白）要完整出現在金標標題之下的某一段內；不切段時就找不到的（引文被「面試」行過濾或表格欄位清空等原因改過）不算被切斷。"
          "全部金標都找不到＝該題一定找不到完整答案句；任一金標被切斷＝至少有一條金標的引文被切在兩段之間。"]
    return "\n".join(L) + "\n"


def report(work, lengths=LENGTHS):
    runs = {n: json.loads((Path(work) / f"chunk_{n}.json").read_text(encoding="utf-8")) for n in lengths}
    res = summarize(runs)
    OUT.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    text = render(res, None)
    OUT.with_suffix(".txt").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, help="只跑這個長度（寫 work/chunk_N.json）")
    ap.add_argument("--work", default=str(default_work()))
    ap.add_argument("--report", action="store_true", help="只用現有的中間結果彙整")
    a = ap.parse_args()
    Path(a.work).mkdir(parents=True, exist_ok=True)
    if a.chunk:
        print(run_one(a.chunk, a.work))
        return
    if not a.report:
        for n in LENGTHS:  # 一次一個子程序，一次只載一個 bge-m3
            if (Path(a.work) / f"chunk_{n}.json").is_file():
                print(f"[{n}] 已有中間結果，跳過")
                continue
            subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__)), "--chunk", str(n), "--work", a.work], check=True)
    report(a.work)


if __name__ == "__main__":
    main()

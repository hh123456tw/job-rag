"""評分器。檢索只透過 search()；金標用「檔名＋標題路徑」定義。"""
import re

from .retrieval import THIRD_PARTY
from .stats import BOOTSTRAP, SEED, gate_outcome, mrr_interval, paired_diff_interval, pick_threshold, verdict


def hit_rank(results: list[dict], golds: list[dict]) -> int | None:
    """前面的結果中第一個落在任一金標標題之下的名次（從 1 起算）；沒有則 None。
    「之下」＝標題路徑相同，或以「金標 > 」開頭。不用子字串。"""
    for i, r in enumerate(results, 1):
        for g in golds:
            for loc in [r, *r.get("also_in", [])]:  # 去重時被合併的位置也算
                h = loc["heading_path"]
                if loc["file"] == g["file"] and (h == g["heading"] or h.startswith(g["heading"] + " > ")):
                    return i
    return None


def metrics(ranks: list[int | None]) -> dict:
    if not ranks:
        raise ValueError("沒有題目，不能算指標")
    n = len(ranks)
    return {
        "n": n,
        "hit@1": sum(r == 1 for r in ranks) / n,
        "hit@3": sum(r is not None and r <= 3 for r in ranks) / n,
        "hit@5": sum(r is not None and r <= 5 for r in ranks) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
    }


DEPTH = 10  # 名次最多看到第 10；更後面算未命中（MRR 也算 0）


def _asked(question: str, co: str | None) -> str:
    """與 retrieval.search 相同：已指定公司而問句沒提到它，就先補上公司名再算分。"""
    return f"{co} {question}" if co and co not in question else question


def _group(questions, method, corpus, detect=False, dedupe=False):
    from . import detect_company, gate_score, retrieval, search
    ranks, top, n_unans, scoped = {}, {}, 0, {}
    for q in questions:
        # 已指定公司：題目自帶 company（公司頁內提問），或開了 detect 且問句只提到一家公司
        co = q.get("company") or (detect_company(q["question"], corpus) if detect else None)
        if co:
            scoped[q["id"]] = co
        if not q["answerable"]:
            n_unans += 1
        else:  # 排名不套門檻：量的是檢索本身
            ranks[q["id"]] = hit_rank(search(q["question"], method=method, company=co, k=DEPTH, corpus=corpus, gate=False,
                                             dedupe=dedupe), q["gold"])
        s = gate_score(_asked(q["question"], co), method, company=co, corpus=corpus)
        if s is not None:
            top[q["id"]] = s
    out = {"ranks": ranks, "metrics": metrics(list(ranks.values())) if ranks else None,
           "gate_scores": top or None,  # 題號 -> 最高分；沒做門檻的方式是 None
           "scoped": scoped,  # 題號 -> 已指定的公司（用較低的門檻）
           "unanswerable": {"n": n_unans, "refusal_rate": None}}
    if top:  # 沒做門檻的方式不假造拒答率
        t = retrieval.NOT_FOUND_THRESHOLD
        ts = round(t - retrieval.SCOPED_DROP, 3)  # 與 app._thr 同一算式
        by = {q["id"]: q["answerable"] for q in questions}
        parts = [gate_outcome({i: s for i, s in top.items() if by[i] and (i in scoped) == sc},
                              {i: s for i, s in top.items() if not by[i] and (i in scoped) == sc}, thr)
                 for sc, thr in ((False, t), (True, ts))]
        order = {i: n for n, i in enumerate(top)}
        got = {k: sorted(parts[0][k] + parts[1][k], key=order.get) for k in parts[0]}
        out["gate"] = {"threshold": t, "scoped_threshold": ts, "scoped_ids": [i for i in top if i in scoped],
                       "thresholds": {i: (ts if i in scoped else t) for i in top}, **got}
        out["unanswerable"] |= {"refusal_rate": len(got["unanswerable_blocked"]) / n_unans if n_unans else None}
    return out


def evaluate(questions: list[dict], method: str = "bge-m3", corpus=None, detect=False, dedupe=False) -> dict:
    """全部題，只查公開事實段落（排除段落不在索引內）。detect／dedupe 是兩個可選開關，預設關。"""
    scores = _group(questions, method, corpus, detect, dedupe)
    types = {}
    for q in questions:
        if q["answerable"]:
            types.setdefault(q.get("type", "未分類"), []).append(scores["ranks"][q["id"]])
    return {"method": method, "scores": scores, "by_type": {t: metrics(r) for t, r in types.items()}}


def _refusal(g) -> str:
    if "gate" not in g:
        return "此方式沒做查無門檻"
    u, gt = g["unanswerable"], g["gate"]
    return (f"查無門檻 {gt['threshold']:.3f}：擋住 {len(gt['unanswerable_blocked'])}/{u['n']} 題不可回答題（正確拒答率 {u['refusal_rate']:.2f}）；"
            f"誤擋 {len(gt['answerable_blocked'])}/{g['metrics']['n']} 題可回答題" if g["metrics"] else "（無可回答題）")


def _fmt(m):
    if m is None:
        return "（無可回答題）"
    return f"題數 {m['n']}  Hit@1 {m['hit@1']:.3f}  Hit@3 {m['hit@3']:.3f}  MRR {m['mrr']:.3f}"


def format_report(rep: dict) -> str:
    out = [f"檢索方式：{rep['method']}　評分單位：段落　Hit@k 的 k=1、3；名次最多看到 {DEPTH}"]
    g = rep["scores"]
    out.append(f"\n## 全部題（只查公開事實段落）\n{_fmt(g['metrics'])}")
    if g["unanswerable"]["n"]:
        out.append(f"不可回答題 {g['unanswerable']['n']} 題；" + _refusal(g))
    for t, m in rep.get("by_type", {}).items():
        out.append(f"  題型 {t}：{_fmt(m)}")
    miss = [i for i, r in g["ranks"].items() if r is None or r > 3]
    if miss:
        out.append("前 3 名未命中：" + "、".join(f"{i}(名次{g['ranks'][i] or '無'})" for i in miss))
    return "\n".join(out)


SUSPICIOUS = "※ 命中率接近 100%：先懷疑題目太簡單，不要當成方法很強"
NEAR_PERFECT = 0.95
TABLE_OUT = "eval/results_methods.txt"


def compare(questions: list[dict], methods=None, corpus=None, detect=False, dedupe=False) -> dict:
    from . import METHODS
    return {m: evaluate(questions, method=m, corpus=corpus, detect=detect, dedupe=dedupe) for m in (methods or METHODS)}


def _interval(rep):
    r = list(rep["scores"]["ranks"].values())
    return mrr_interval(r) if r else None


def _gate_cell(g) -> str:
    if "gate" not in g:
        return "沒做門檻"
    gt = g["gate"]
    return f"擋住 {len(gt['unanswerable_blocked'])}/{g['unanswerable']['n']}　誤擋 {len(gt['answerable_blocked'])}/{g['metrics']['n']}"


def format_table(reps: dict) -> str:
    out = [f"檢索方式並列　評分單位：段落　只查公開事實段落　Hit@k 的 k=1、3、5；名次最多看到 {DEPTH}",
           "排名不套查無門檻（量檢索本身）；最右欄是套門檻後：擋住＝不可回答題被擋住，誤擋＝可回答題被擋掉",
           f"{'方式':<14}{'題數':>4}{'Hit@1':>8}{'Hit@3':>8}{'Hit@5':>8}{'MRR':>8}  {'MRR 95% 區間':<16}查無（擋住／誤擋）"]
    flagged = False
    for name, rep in reps.items():
        m = rep["scores"]["metrics"]
        if m is None:
            out.append(f"{name:<14}（無可回答題）")
            continue
        flagged |= m["hit@1"] >= NEAR_PERFECT or m["hit@3"] >= NEAR_PERFECT
        iv = _interval(rep)
        out.append(f"{name:<14}{m['n']:>4}{m['hit@1']:>8.3f}{m['hit@3']:>8.3f}{m['hit@5']:>8.3f}{m['mrr']:>8.3f}  "
                   f"{('[%.3f, %.3f]' % iv) if iv else '-':<16}{_gate_cell(rep['scores'])}")
    if flagged:
        out.append(SUSPICIOUS)
    return "\n".join(out)


def format_interval_note(reps: dict) -> str:
    n = next(iter(reps.values()))["scores"]["metrics"]["n"]
    out = ["## 信賴區間",
           f"題少（可回答題只有 {n} 題），所以把題目重抽 {BOOTSTRAP} 次（可重複抽、固定亂數種子 {SEED}），"
           "每次算一次 MRR，取中間 95% 的範圍；區間越寬，越不能肯定成績。"]
    a, b = reps.get("bge-m3"), reps.get("hybrid")
    if a and b and a["scores"]["ranks"].keys() == b["scores"]["ranks"].keys() and a["scores"]["ranks"]:
        iv = paired_diff_interval(list(a["scores"]["ranks"].values()), list(b["scores"]["ranks"].values()))
        d = a["scores"]["metrics"]["mrr"] - b["scores"]["metrics"]["mrr"]
        out.append(f"bge-m3 減 hybrid 的 MRR 差：{d:+.3f}，95% 區間 [{iv[0]:+.3f}, {iv[1]:+.3f}]（兩者用同一批重抽的題目）。{verdict(iv)}。")
    return "\n".join(out)


def _sweep(top: dict, answerable: set, chosen: float) -> list[str]:
    ts = sorted({0.60, 0.65, 0.70, 0.75, round(chosen, 3)})
    rows = [f"{'門檻':>6}  擋住不可回答題  誤擋可回答題"]
    for t in ts:
        o = gate_outcome({i: s for i, s in top.items() if i in answerable},
                         {i: s for i, s in top.items() if i not in answerable}, t)
        n_u = len(o["unanswerable_blocked"]) + len(o["unanswerable_passed"])
        rows.append(f"{t:>6.3f}  {len(o['unanswerable_blocked']):>2}/{n_u:<12}{len(o['answerable_blocked']):>2}/{len(answerable)}")
    return rows


def _gate_block(questions, top, ans, gt, T, ids, label=""):
    """一組題（同一個門檻）的查無結果。ids＝這組題的題號。"""
    n_u = sum(i not in ans for i in ids)
    n_a = sum(i in ans for i in ids)
    bu = [i for i in gt["unanswerable_blocked"] if i in ids]
    pu = [i for i in gt["unanswerable_passed"] if i in ids]
    ba = [i for i in gt["answerable_blocked"] if i in ids]
    out = [f"結果{label}（門檻 {T:.3f}，bge-m3 與混合相同）：",
           f"  不可回答題擋住 {len(bu)}/{n_u}：{'、'.join(bu) or '無'}；沒擋住：{'、'.join(pu) or '無'}",
           f"  可回答題誤擋 {len(ba)}/{n_a}" + (f"（{len(ba) / n_a:.0%}）" if n_a else "") + f"：{'、'.join(ba) or '無'}"]
    passed_a = [s for i, s in top.items() if i in ids and i in ans and s >= T]
    if bu and passed_a:
        out.append(f"貼線：擋住的不可回答題最高分 {max(top[i] for i in bu):.4f}，放行的可回答題最低分 {min(passed_a):.4f}；兩者越近，門檻越是貼著這批題擬合。")
    out.append("門檻越高，擋住越多不可回答題，也誤擋越多可回答題：")
    out += ["  " + r for r in _sweep({i: s for i, s in top.items() if i in ids}, ans & set(ids), T)]
    return out


def format_gate(questions: list[dict], reps: dict) -> str:
    from . import retrieval
    T = retrieval.NOT_FOUND_THRESHOLD
    out = ["## 查無",
           f"做法：最高分低於門檻就回查無。門檻是 bge-m3 的最高相似度：未指定公司 {T:.3f}；已指定公司（公司頁內提問，或問句只提到一家公司）"
           f"降 {retrieval.SCOPED_DROP:.2f}，用 {round(T - retrieval.SCOPED_DROP, 3):.3f}。混合也用它的 bge-m3 最高分判斷"
           "（混合自己的 RRF 分數只看名次，不代表有多像，沒辦法比門檻）。BM25、bge-small-zh、e5-large 的分數尺度不同，沒做門檻。",
           "挑法：試每個相鄰分數的中點，選「可回答題放行率＋不可回答題擋住率」最高者，同分取較低；兩種題各算比率，因為兩種題的題數差很多。",
           "限制：門檻用評估的同一批題挑，沒有獨立測試題，所以下面的數字是用挑門檻的題目打分，偏樂觀，只能當方向。"]
    rep = reps.get("bge-m3")
    top = rep and rep["scores"].get("gate_scores")
    if not top:
        return "\n".join(out + ["（沒有 bge-m3 的結果，無法列出查無表現）"])
    ans = {q["id"] for q in questions if q["answerable"]}
    g = rep["scores"]
    gt = g["gate"]
    sc = set(gt.get("scoped_ids", []))
    if not sc:  # 沒有已指定公司的題：只有一個門檻
        try:
            picked = pick_threshold([s for i, s in top.items() if i in ans], [s for i, s in top.items() if i not in ans])
            out.append(f"重算挑出的門檻：{picked:.4f}；程式內使用：{T:.3f}。")
        except ValueError as e:
            out.append(f"重算門檻失敗：{e}")
        return "\n".join(out + _gate_block(questions, top, ans, gt, T, set(top)))
    ts = gt["scoped_threshold"]
    out.append("兩組題各用自己的門檻，下面分開列（已指定公司 "
               f"{len(sc)} 題，未指定公司 {len(top) - len(sc)} 題）；不重算挑門檻，因為未指定公司的題裡常常沒有不可回答題。")
    out += _gate_block(questions, top, ans, gt, T, set(top) - sc, "：未指定公司")
    out += _gate_block(questions, top, ans, gt, ts, sc, "：已指定公司")
    return "\n".join(out)


DEEP = re.compile(r"^\d\d_")  # 一公司一檔的深查檔；其餘（A_、B_、補、網址）是 104 職缺檔


def format_interview(drops: list[dict]) -> str:
    pub = [d for d in drops if d["public"]]
    third = [d for d in pub if THIRD_PARTY.search(d["line"])]
    job = [d for d in pub if d not in third and not DEEP.match(d["file"])]
    other = [d for d in pub if d not in third and d not in job]
    show = lambda d: f"  {d['file']} > {d['heading_path'][:30]} | {d['line'][:50]}"
    out = ["## 「面試」行過濾",
           "做法：載入語料時，內文含「面試」二字的行丟掉（面試資訊不屬公開事實）。表格列只清空含「面試」的欄位，保留職缺名稱、網址等其他欄位；第三方面試網站的表格列與非表格行整行丟掉。標題行不丟，否則排除段落的內容會併進上一段。逐行判斷見 eval/line_filter_review.md。",
           f"丟掉 {len(drops)} 行；其中在公開事實段落內 {len(pub)} 行，其餘 {len(drops) - len(pub)} 行本來就在排除段落。",
           f"公開段落內的 {len(pub)} 行：第三方面試心得或面試網站 {len(third)} 行（本來就不是公司公開事實）；"
           f"104 職缺檔 {len(job)} 行（最可能真的丟了公開職缺內容，逐行列出）；"
           f"其他 {len(other)} 行（多為「面試時要問」「面試前請核對」這類提醒語，列前 3 行）。"]
    out += [show(d) for d in job] + [show(d) for d in other[:3]]
    out.append("誤丟風險：非表格行整行丟掉，同一行的公開內容（「優先面試」這類條件）也一起沒了；"
               "表格列的「面試」欄位內若同時寫了工具、人數、地點，也會一起沒了。全部列出：python -X utf8 -m job_rag.classify")
    return "\n".join(out)


TOGGLES_OUT = "eval/results_toggles.txt"
CONFIGS = [("全關（基準）", False, False), ("只開公司名過濾", True, False), ("只開去重", False, True), ("兩個都開", True, True)]


def toggle_runs(questions, method="bge-m3", corpus=None) -> dict:
    return {name: evaluate(questions, method=method, corpus=corpus, detect=d, dedupe=u) for name, d, u in CONFIGS}


def format_toggles(runs: dict) -> str:
    """每種開關組合的 Hit@1、Hit@3、MRR（各附 95% 區間），以及和基準相比的差（同一批重抽題目）。"""
    from .stats import metric_interval, paired_metric_interval
    base = next(iter(runs.values()))
    out = [f"開關比較　檢索方式：{base['method']}　可回答題 {base['scores']['metrics']['n']} 題　名次最多看到 {DEPTH}",
           f"區間＝題目重抽 {BOOTSTRAP} 次（種子 {SEED}）的 95% 範圍；差＝該組合減基準，括號是差的 95% 區間。規則沒有為了成績調整，好壞照列。"]
    for name, rep in runs.items():
        m, r = rep["scores"]["metrics"], list(rep["scores"]["ranks"].values())
        cells = "　".join(f"{label} {m[k]:.3f} [%.3f, %.3f]" % metric_interval(r, k)
                          for k, label in (("hit@1", "Hit@1"), ("hit@3", "Hit@3"), ("mrr", "MRR")))
        out.append(f"{name}：{cells}　查無：{_gate_cell(rep['scores'])}")
    br = list(base["scores"]["ranks"].values())
    out.append("\n和基準相比（差，95% 區間）：")
    for name, rep in list(runs.items())[1:]:
        r, m, bm = list(rep["scores"]["ranks"].values()), rep["scores"]["metrics"], base["scores"]["metrics"]
        cells = []
        for k, label in (("hit@1", "Hit@1"), ("hit@3", "Hit@3"), ("mrr", "MRR")):
            lo, hi = paired_metric_interval(r, br, k)
            cells.append(f"{label} {m[k] - bm[k]:+.3f} [{lo:+.3f}, {hi:+.3f}]")
        out.append(f"  {name}：" + "　".join(cells))
    out.append("\n名次有變的題（基準名次→新名次，無＝前 10 名沒有）：")
    for name, rep in list(runs.items())[1:]:
        ch = [f"{i}({base['scores']['ranks'][i] or '無'}→{x or '無'})" for i, x in rep["scores"]["ranks"].items()
              if x != base["scores"]["ranks"][i]]
        out.append(f"  {name}：{'、'.join(ch) or '無'}")
    return "\n".join(out)


def questions_digest(questions: list[dict]) -> str:
    """題組的指紋（題號、題目、可否回答、金標）。題組一變，舊輸出檔的指紋就對不上。"""
    import hashlib
    import json
    key = [[q["id"], q["question"], q["answerable"], q.get("gold", [])] for q in questions]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def results_json(questions: list[dict], reps: dict, settings: dict | None = None) -> dict:
    """給專案說明頁讀的逐題輸出：每種方式的指標、各指標 95% 區間、逐題名次、查無結果。與 results_methods.txt 同一次執行。"""
    from .stats import metric_interval
    methods = {}
    for name, rep in reps.items():
        sc = rep["scores"]
        m, ranks = sc["metrics"], sc["ranks"]
        methods[name] = {
            **{k: m[k] for k in ("hit@1", "hit@3", "hit@5", "mrr")},
            "ci": {k: list(metric_interval(list(ranks.values()), k)) for k in ("hit@1", "hit@3", "hit@5", "mrr")},
            "ranks": ranks, "gate": sc.get("gate"), "gate_scores": sc.get("gate_scores"), "scoped": sc.get("scoped", {}),
        }
    return {"digest": questions_digest(questions), "depth": DEPTH, "bootstrap": BOOTSTRAP, "seed": SEED,
            "n_answerable": sum(q["answerable"] for q in questions),
            "n_unanswerable": sum(not q["answerable"] for q in questions), "settings": settings or {}, "methods": methods}


def format_settings(settings: dict) -> str:
    from . import retrieval
    onoff = lambda b: "開" if b else "關"
    return (f"量測設定：公司名自動偵測 {onoff(settings['detect'])}、結果去重 {onoff(settings['dedupe'])}（網站兩個開關預設都開）；"
            f"網站每題取前 K={retrieval.DEFAULT_K} 段（Hit@5＝K 段內有金標）；已指定公司的問句沒提到公司名時，先補上公司名再檢索。")


def format_results(questions: list[dict], reps: dict, drops: list[dict], settings: dict | None = None) -> str:
    head = [format_settings(settings)] if settings else []
    return "\n\n".join(head + [format_table(reps), format_interval_note(reps), format_gate(questions, reps), format_interview(drops)])


def main():
    import argparse
    import json
    from pathlib import Path
    from .evalset import questions_path
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(questions_path()))
    ap.add_argument("--method", default="bge-m3", help="bm25、bge-small-zh、bge-m3、e5-large、hybrid，或 all")
    ap.add_argument("--out", help="all 時預設寫入 " + TABLE_OUT)
    ap.add_argument("--detect", action="store_true", help="開公司名自動過濾")
    ap.add_argument("--dedupe", action="store_true", help="開結果去重")
    ap.add_argument("--toggles", action="store_true", help="四種開關組合並列，寫入 " + TOGGLES_OUT)
    a = ap.parse_args()
    qs = json.loads(Path(a.questions).read_text(encoding="utf-8"))["questions"]
    if a.toggles:
        text = format_toggles(toggle_runs(qs, method=a.method))
        Path(a.out or TOGGLES_OUT).write_text(text + "\n", encoding="utf-8")
        print(text)
    elif a.method == "all":  # 要代表網站現在這版，請加 --detect --dedupe
        from . import interview_drops
        settings = {"detect": a.detect, "dedupe": a.dedupe}
        reps = compare(qs, detect=a.detect, dedupe=a.dedupe)
        text = format_results(qs, reps, interview_drops(), settings)
        out = Path(a.out or TABLE_OUT)
        out.write_text(text + "\n", encoding="utf-8")
        out.with_suffix(".json").write_text(json.dumps(results_json(qs, reps, settings), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(text)
        print(f"\n已寫入 {out}")
    else:
        print(format_report(evaluate(qs, method=a.method, detect=a.detect, dedupe=a.dedupe)))


if __name__ == "__main__":
    main()

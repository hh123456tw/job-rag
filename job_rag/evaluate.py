"""評分器。檢索只透過 search()；金標用「檔名＋標題路徑」定義。"""


def hit_rank(results: list[dict], golds: list[dict]) -> int | None:
    """前面的結果中第一個落在任一金標標題之下的名次（從 1 起算）；沒有則 None。
    「之下」＝標題路徑相同，或以「金標 > 」開頭。不用子字串。"""
    for i, r in enumerate(results, 1):
        for g in golds:
            h = r["heading_path"]
            if r["file"] == g["file"] and (h == g["heading"] or h.startswith(g["heading"] + " > ")):
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
        "mrr": sum(1 / r for r in ranks if r) / n,
    }


DEPTH = 10  # 名次最多看到第 10；更後面算未命中（MRR 也算 0）
QUESTIONS = "eval/questions.json"


def _group(questions, mode, method, corpus):
    from . import search
    ranks, n_unans = {}, 0
    for q in questions:
        if not q["answerable"]:
            n_unans += 1
            continue
        res = search(q["question"], method=method, mode=mode, k=DEPTH, corpus=corpus)
        ranks[q["id"]] = hit_rank(res, q["gold"])
    return {
        "ranks": ranks,
        "metrics": metrics(list(ranks.values())) if ranks else None,
        # 此票沒有查無門檻：不假造拒答率
        "unanswerable": {"n": n_unans, "refusal_rate": None},
    }


def evaluate(questions: list[dict], method: str = "bm25", corpus=None) -> dict:
    """全部題，只查公開事實段落（排除段落不在索引內）。"""
    return {"method": method, "scores": _group(questions, "demo", method, corpus)}


def _fmt(m):
    if m is None:
        return "（無可回答題）"
    return f"題數 {m['n']}  Hit@1 {m['hit@1']:.3f}  Hit@3 {m['hit@3']:.3f}  MRR {m['mrr']:.3f}"


def format_report(rep: dict) -> str:
    out = [f"檢索方式：{rep['method']}　評分單位：段落　Hit@k 的 k=1、3；名次最多看到 {DEPTH}"]
    g = rep["scores"]
    out.append(f"\n## 全部題（只查公開事實段落）\n{_fmt(g['metrics'])}")
    if g["unanswerable"]["n"]:
        out.append(f"不可回答題 {g['unanswerable']['n']} 題；正確拒答率：尚未實作門檻")
    miss = [i for i, r in g["ranks"].items() if r is None or r > 3]
    if miss:
        out.append("前 3 名未命中：" + "、".join(f"{i}(名次{g['ranks'][i] or '無'})" for i in miss))
    return "\n".join(out)


SUSPICIOUS = "※ 命中率接近 100%：先懷疑題目太簡單，不要當成方法很強"
NEAR_PERFECT = 0.95
TABLE_OUT = "eval/results_methods.txt"


def compare(questions: list[dict], methods=None, corpus=None) -> dict:
    from . import METHODS
    return {m: evaluate(questions, method=m, corpus=corpus) for m in (methods or METHODS)}


def format_table(reps: dict) -> str:
    out = [f"檢索方式並列　評分單位：段落　只查公開事實段落　Hit@k 的 k=1、3；名次最多看到 {DEPTH}",
           f"{'方式':<14}{'題數':>4}{'Hit@1':>8}{'Hit@3':>8}{'MRR':>8}"]
    flagged = False
    for name, rep in reps.items():
        m = rep["scores"]["metrics"]
        if m is None:
            out.append(f"{name:<14}（無可回答題）")
            continue
        flagged |= m["hit@1"] >= NEAR_PERFECT or m["hit@3"] >= NEAR_PERFECT
        out.append(f"{name:<14}{m['n']:>4}{m['hit@1']:>8.3f}{m['hit@3']:>8.3f}{m['mrr']:>8.3f}")
    n = next(iter(reps.values()))["scores"]["unanswerable"]["n"]
    out.append(f"\n不可回答題 {n} 題；正確拒答率：尚未實作門檻")
    if flagged:
        out.append(SUSPICIOUS)
    return "\n".join(out)


def main():
    import argparse
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=QUESTIONS)
    ap.add_argument("--method", default="bm25", help="bm25、bge-small-zh、bge-m3、e5-large、hybrid，或 all")
    ap.add_argument("--out", help="all 時預設寫入 " + TABLE_OUT)
    a = ap.parse_args()
    qs = json.loads(Path(a.questions).read_text(encoding="utf-8"))["questions"]
    if a.method == "all":
        text = format_table(compare(qs))
        out = Path(a.out or TABLE_OUT)
        out.write_text(text + "\n", encoding="utf-8")
        print(text)
        print(f"\n已寫入 {out}")
    else:
        print(format_report(evaluate(qs, method=a.method)))


if __name__ == "__main__":
    main()

"""專案說明頁的資料層：只讀既有評估輸出檔，不重算、不呼叫外部 API。
檔缺、解析失敗、或和現在的題組對不上（輸出檔過期），一律丟 AboutDataError，不回舊數字或預設值。"""
import json
from pathlib import Path

from . import METHODS
from .evaluate import questions_digest
from .evalset import questions_path
from .generation import FAILED, GATED, SCORED, summarize

ROOT = Path(__file__).parent.parent
FOUND = 3  # Hit@3：前 3 名內有金標段落才算找到
CONSISTENT = 0.05  # GPT 複查與 RAGAS 的忠實度平均差在這個範圍內，才說「一致」


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
        out.append({"method": m, **{k: methods[m][k] for k in ("hit@1", "hit@3", "mrr", "ci")}})
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
    blocked = [{"kind": "blocked", "id": i, "score": scores[i], "threshold": g["threshold"],
                "rank": methods["bge-m3"]["ranks"][i]} for i in g["answerable_blocked"]]
    blocked.sort(key=lambda c: (c["threshold"] - c["score"], c["id"]))
    picked = miss[:1] + blocked[:1]
    picked += (miss[1:] + blocked[1:])[: 2 - len(picked)]
    return [c | {"question": by[c["id"]]["question"], "gold": by[c["id"]]["gold"]} for c in picked]


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
    return {
        "n_answerable": m["n_answerable"], "n_unanswerable": m["n_unanswerable"],
        "bootstrap": m["bootstrap"], "depth": m["depth"], "table": table,
        "generation": gen and {k: v for k, v in gen.items() if k != "scored_ids"}, "cross": cross,
        "gate": {"threshold": gate["threshold"], "unanswerable_blocked": len(gate["unanswerable_blocked"]),
                 "n_unanswerable": m["n_unanswerable"], "answerable_blocked": len(gate["answerable_blocked"]),
                 "n_answerable": m["n_answerable"]},
        "cases": _cases(questions, m["methods"], table),
    }

"""跨公司路徑：混合挑段 對 只用 bge-m3 挑段。python -X utf8 eval/run_cross_mrr.py
兩組有答案的跨公司題都算，再合計：
  held  eval/questions_heldout.json 裡走跨公司路徑的題（Codex 出，全是技術名詞）
  old   eval/questions_cross.json（我自己出，含薪水、技術、出差、新聞等）
  val   eval/questions_cross_val.json（Codex 出，直白問法、五種題型；出完沒有用來調任何東西）
  all   三組合計（只留在輸出檔，簡報不用）
每一題的每一家「該出現的公司」（公開段落含關鍵字、且有按鈕的公司）算一筆：
  取到＝那一家前 PER_COMPANY 名內有含關鍵字的段落；
  MRR＝那一家第一個含關鍵字的段落排第幾名，取倒數後對所有筆平均（只看前 DEPTH 名，更後面算 0）。
另記每組被查無門檻擋住的題數（照網站現行路徑）。只量不調，不呼叫 LLM。
自我檢查：held 的混合取到家數要等於 eval/results_heldout.json 的數字。
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
METHODS = ("hybrid", "bge-m3")
NAME = {"held": "Codex 出的技術名詞題（刻意換說法）", "old": "我自己出的跨公司題", "val": "Codex 出的驗證題（直白問法，沒用來調參）", "all": "三組合計"}


def load(name):
    return json.loads((ROOT / "eval" / name).read_bytes().decode("utf-8"))["questions"]


def measure(qs, root, live):
    """回 (逐題列, 各方法的倒數名次清單)。"""
    rows, rr = [], {m: [] for m in METHODS}
    for q in qs:
        pool, rv = R._rank_vector(root, "bge-m3", q["question"], None)
        _, rb = R._rank_bm25(root, q["question"], None)
        orders = {"bge-m3": [i for i, _ in rv], "hybrid": [i for i, _ in R.rrf([[i for i, _ in rb], [i for i, _ in rv]])]}
        rel = sorted({s["company"] for s in pool if s["company"] in live and run_real.has(s["text"], q["keywords"])})
        row = {"id": q["id"], "question": q["question"], "keywords": q["keywords"], "n_relevant": len(rel),
               "blocked": app._low_cross(app._cross_hits(q["question"], "demo")), "ranks": {}}
        for m, order in orders.items():
            row["ranks"][m] = {}
            for c in rel:
                mine = [i for i in order if pool[i]["company"] == c]
                r = next((n for n, i in enumerate(mine[:DEPTH], 1) if run_real.has(pool[i]["text"], q["keywords"])), None)
                row["ranks"][m][c] = r
                rr[m].append(1 / r if r else 0.0)
        rows.append(row)
    return rows, rr


def summary(rows, rr, per):
    out = {"n": len(rows), "pairs": len(rr["hybrid"]), "blocked": sum(r["blocked"] for r in rows)}
    for m in METHODS:
        ranks = [r for row in rows for r in row["ranks"][m].values()]
        out[m] = {"mrr": sum(rr[m]) / len(rr[m]), "got": sum(r is not None and r <= per for r in ranks), "first": sum(r == 1 for r in ranks)}
    return out


def main():
    held_all = load("questions_heldout.json")
    sets = {"held": [q for q in held_all if q["answerable"] and run_real.route(q) == "跨公司"],
            "old": [q for q in load("questions_cross.json") if q["answerable"]],
            "val": [q for q in load("questions_cross_val.json") if q["answerable"]]}
    root, live, per = R._root(None, "demo"), {n for _, n in app._company_buttons()}, R.PER_COMPANY
    out = {"date": datetime.date.today().isoformat(), "digest": {"held": questions_digest(held_all), "old": questions_digest(load("questions_cross.json"))},
           "depth": DEPTH, "per_company": per, "cross_floor": R.CROSS_FLOOR, "sets": {}, "rows": {}}
    allrows, allrr = [], {m: [] for m in METHODS}
    for k, qs in sets.items():
        rows, rr = measure(qs, root, live)
        out["sets"][k], out["rows"][k] = summary(rows, rr, per), rows
        allrows += rows
        for m in METHODS:
            allrr[m] += rr[m]
    out["sets"]["all"] = summary(allrows, allrr, per)
    ok = [r for r in allrows if not r["blocked"] and r["n_relevant"]]
    e = max(ok, key=lambda r: r["n_relevant"])  # 例題：放行的題裡，該出現公司最多的那題
    out["example"] = {"q": e["question"], "kw": "、".join(e["keywords"]), "want": e["n_relevant"],
                      "got": sum(r is not None and r <= per for r in e["ranks"]["hybrid"].values())}
    held = json.loads((ROOT / "eval/results_heldout.json").read_text(encoding="utf-8"))
    out["check_held_matches_results_heldout"] = out["sets"]["held"]["hybrid"]["got"] == sum(x["n_correct"] for x in held["cross"] if x["answerable"])
    OUT.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    L = [f"跨公司路徑：混合挑段 對 只用 bge-m3 挑段。量測日期 {out['date']}。每家取 {per} 段；MRR 每家只看前 {out['depth']} 名；門檻 CROSS_FLOOR = {out['cross_floor']}。",
         "一筆＝一題裡的一家「該出現的公司」。取到＝那一家前幾名內有含關鍵字的段落；MRR＝第一個含關鍵字的段落在那一家排第幾名，取倒數後平均。", "",
         "題組　題數　被門檻擋住　混合：取到／MRR／排第 1 名　只用 bge-m3：取到／MRR／排第 1 名"]
    for k, v in out["sets"].items():
        h, b = v["hybrid"], v["bge-m3"]
        L.append(f"{NAME[k]}　{v['n']}　{v['blocked']}　{h['got']}/{v['pairs']}／{h['mrr']:.3f}／{h['first']}/{v['pairs']}　{b['got']}/{v['pairs']}／{b['mrr']:.3f}／{b['first']}/{v['pairs']}")
    L += ["", f"自我檢查：Codex 那組的混合取到家數與 eval/results_heldout.json 一致：{'是' if out['check_held_matches_results_heldout'] else '否'}", "", "題組 題號 該出現 混合取到 bge-m3取到 被擋 問句"]
    for k in ("held", "old", "val"):
        for r in out["rows"][k]:
            g = {m: sum(x is not None and x <= per for x in r["ranks"][m].values()) for m in METHODS}
            L.append(f"{NAME[k]} {r['id']} {r['n_relevant']} {g['hybrid']} {g['bge-m3']} {'是' if r['blocked'] else '否'} {r['question']}")
    L += ["", "== 限制 ==", "「含關鍵字」是字面比對，換說法的題會吃虧，也偏向 BM25。兩組題都已用來調過跨公司門檻或挑段方式，數字偏樂觀。"
          "Codex 那組由單一模型出；另一組是我自己出的；標準答案都沒有人工確認。跨公司的 MRR 不能和問一家公司的 MRR 直接比（判斷正確的方式不同）。"]
    OUT.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:9]))


if __name__ == "__main__":
    main()

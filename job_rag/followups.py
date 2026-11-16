"""追問題迷你評估（票 22）：量「不補全」與「補全」兩種做法的 Hit@3，只量檢索，不量多輪答案品質。
python -X utf8 -m job_rag.followups            # 核對引文、評分、寫 eval/results_followups.json（需 JOB_RAG_CORPUS 與模型）
題目在 eval/followups.json；金標用檔名＋標題路徑，引文用 evalset.verify 核對真的在金標之下。"""
import hashlib
import json
import sys
from pathlib import Path

from .evalset import verify
from .evaluate import DEPTH, hit_rank
from .memory import expand
from .retrieval import detect_company, search

ROOT = Path(__file__).parent.parent
QUESTIONS, RESULTS = "eval/followups.json", "eval/results_followups.json"
FOUND = 3  # Hit@3


def digest(questions: list[dict]) -> str:
    """題組指紋：題號、前一題、追問、範圍、金標。題組一變，舊輸出檔對不上。"""
    key = [[q["id"], q["company"], q["previous"], q["question"], q["gold"]] for q in questions]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _rank(query: str, scope: str, gold, method, corpus):
    """與 app 的 /api/search 同一套：範圍是單一公司就只搜那家；全部公司就從問句偵測公司。不套查無門檻、去重開。"""
    company = scope or detect_company(query, corpus)
    return hit_rank(search(query, method=method, company=company, k=DEPTH, gate=False, dedupe=True, corpus=corpus), gold)


def _mode(ranks: dict) -> dict:
    n = len(ranks)
    found = sum(r is not None and r <= FOUND for r in ranks.values())
    return {"found": found, "hit@3": found / n, "ranks": ranks}


def run(questions: list[dict], method: str = "bge-m3", corpus=None) -> dict:
    plain, comp, expanded = {}, {}, []
    for q in questions:
        rq = expand(q["question"], [{"q": q["previous"]}], corpus)
        if rq != q["question"].strip():
            expanded.append(q["id"])
        plain[q["id"]] = _rank(q["question"], q["company"], q["gold"], method, corpus)
        comp[q["id"]] = _rank(rq, q["company"], q["gold"], method, corpus)
    return {"digest": digest(questions), "n": len(questions), "depth": DEPTH, "method": method, "expanded_ids": expanded,
            "no_expand": _mode(plain), "expand": _mode(comp)}


def main():
    qs = json.loads((ROOT / QUESTIONS).read_text(encoding="utf-8"))["questions"]
    probs = verify(qs)
    if probs:
        print("\n".join(probs))
        sys.exit(1)
    out = run(qs)
    (ROOT / RESULTS).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out['n']} 題；規則補全了 {len(out['expanded_ids'])} 題；"
          f"Hit@3 不補全 {out['no_expand']['found']}/{out['n']}，補全 {out['expand']['found']}/{out['n']}")


if __name__ == "__main__":
    main()

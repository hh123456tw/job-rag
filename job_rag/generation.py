"""生成層評估：search() → 查無則不呼叫 LLM → answer() → RAGAS 評審。
流程只靠三個可替換的函式（search_fn、answer_fn、score_fn），測試用替身，不打 API。"""
import csv
import io
import math
import random

from .answer import NOT_FOUND, SYSTEM, AnswerError, format_source

SCORED, FAILED, GATED = "已評分", "評估失敗", "被查無門檻擋住"
MODEL_NF, ANSWERED = "生成回查無", "已回答（不計分）"
METRICS = ("faithfulness", "answer_relevancy")
OUT = "eval/results_generation.txt"
REVIEW_OUT = "eval/review_sample.csv"
REVIEW_COLS = ["題號", "問題", "答案", "引用段落", "是否忠於出處（使用者填）"]
NOTE = ("評審與生成都是 DeepSeek：同一個模型評自己寫的答案，分數可能偏高（自我偏好）。"
        "題數少（可回答題只有幾十題以內），分數只能當方向，不能當精確數字。"
        "分數要和人工抽查 10 題對照後才可信。")


def _ok(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def run_eval(questions, search_fn, answer_fn, score_fn) -> list[dict]:
    """search_fn(q)->hits；answer_fn(q,hits)->{"answer",...}（失敗丟 AnswerError）；
    score_fn(q,answer,contexts)->{"faithfulness","answer_relevancy"}（失敗丟例外或回非數字）。
    API 失敗與評審失敗一律標「評估失敗」，不補分數。不可回答題只生成、不評分。"""
    rows = []
    for q in questions:
        row = {"id": q["id"], "question": q["question"], "answerable": q["answerable"], "status": None,
               "answer": None, "hits": [], "contexts": [], "error": None, "faithfulness": None, "answer_relevancy": None}
        rows.append(row)
        hits = search_fn(q["question"])
        if not hits:
            row["status"] = GATED
            continue
        row["hits"] = [{k: h[k] for k in ("company", "file", "heading_path", "text")} for h in hits]
        row["contexts"] = [format_source(i, h) for i, h in enumerate(hits, 1)]
        try:
            text = answer_fn(q["question"], hits)["answer"]
        except AnswerError as e:
            row["status"], row["error"] = FAILED, f"生成失敗：{e}"
            continue
        if text == NOT_FOUND:
            row["status"] = MODEL_NF
            continue
        row["answer"] = text
        if not q["answerable"]:
            row["status"] = ANSWERED
            continue
        try:
            s = score_fn(q["question"], text, row["contexts"])
            vals = {m: s[m] for m in METRICS}
            if not all(_ok(v) for v in vals.values()):
                raise ValueError(f"評審回傳非數字分數：{vals}")
        except Exception as e:  # 評審端各種失敗（逾時、格式錯、金鑰）都不補分
            row["status"], row["error"] = FAILED, f"評審失敗：{type(e).__name__}: {e}"
            continue
        row.update(vals, status=SCORED)
    return rows


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def summarize(rows: list[dict]) -> dict:
    ans = [r for r in rows if r["answerable"]]
    un = [r for r in rows if not r["answerable"]]
    ids = lambda rs, st: [r["id"] for r in rs if r["status"] == st]
    scored = [r for r in ans if r["status"] == SCORED]
    return {
        "answerable": {"n": len(ans), "scored": len(scored), "failed": ids(ans, FAILED),
                       "gated": ids(ans, GATED), "model_not_found": ids(ans, MODEL_NF)},
        "unanswerable": {"n": len(un), "refused": sum(r["status"] in (GATED, MODEL_NF) for r in un),
                         "failed": ids(un, FAILED)},
        **{m: _mean([r[m] for r in scored]) for m in METRICS},
    }


def _f(x):
    return "-" if x is None else f"{x:.3f}"


def format_report(rows: list[dict], header: str = "") -> str:
    s = summarize(rows)
    a, u = s["answerable"], s["unanswerable"]
    out = [header] if header else []
    out += ["生成層評估（RAGAS）　指標：faithfulness（忠實度）、answer relevancy（答案相關性）　檢索：search() 預設（bge-m3）",
            "流程：search() → 被查無門檻擋住就不呼叫 LLM → answer() 生成 → RAGAS 評審。只送公開事實段落。",
            "", "## 可回答題逐題", f"{'題號':<6}{'狀態':<14}{'忠實度':>8}{'答案相關性':>10}  備註"]
    for r in rows:
        if r["answerable"]:
            out.append(f"{r['id']:<6}{r['status']:<14}{_f(r['faithfulness']):>8}{_f(r['answer_relevancy']):>10}  {r['error'] or ''}")
    out += ["", "## 平均（只算「已評分」的題）",
            f"可回答題 {a['n']} 題：已評分 {a['scored']} 題；評估失敗 {len(a['failed'])} 題"
            f"{'（' + '、'.join(a['failed']) + '）' if a['failed'] else ''}；"
            f"被查無門檻擋住 {len(a['gated'])} 題；生成回查無 {len(a['model_not_found'])} 題。",
            f"faithfulness 平均 {_f(s['faithfulness'])}　answer relevancy 平均 {_f(s['answer_relevancy'])}"]
    if a["gated"] or a["model_not_found"]:
        out += ["", "## 沒有被打分的可回答題（沒補預設分數，也不在平均內）"]
        if a["gated"]:
            out.append(f"被查無門檻擋住（{len(a['gated'])} 題，檢索端的誤擋，見 eval/results_methods.txt）：{'、'.join(a['gated'])}")
        if a["model_not_found"]:
            out.append(f"檢索放行但生成模型回「查無」（{len(a['model_not_found'])} 題）：{'、'.join(a['model_not_found'])}")
    out += ["", "## 不可回答題（只看拒答，不計入平均）",
            f"{u['n']} 題中回「查無」{u['refused']} 題（含被門檻擋住）；評估失敗 {len(u['failed'])} 題"
            f"{'（' + '、'.join(u['failed']) + '）' if u['failed'] else ''}；"
            f"其餘 {u['n'] - u['refused'] - len(u['failed'])} 題給了答案。"]
    out += ["", "## 限制", NOTE]
    return "\n".join(out)


def review_sample(rows: list[dict], n: int = 10, seed: int = 0) -> list[dict]:
    """從「有生成答案」的題隨機抽 n 題；固定種子，與輸入順序無關；不足 n 題就全取。"""
    pool = sorted((r for r in rows if r["answer"]), key=lambda r: r["id"])
    return sorted(random.Random(seed).sample(pool, min(n, len(pool))), key=lambda r: r["id"])


def format_review(sample: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(REVIEW_COLS)
    for r in sample:
        cites = "\n\n".join(f"[{i}] {h['company']} / {h['file']} / {h['heading_path']}\n{h['text']}"
                            for i, h in enumerate(r["hits"], 1))
        w.writerow([r["id"], r["question"], r["answer"], cites, ""])
    return buf.getvalue()


# ---- 乾跑估算：不打 API ----
PRICE = {  # 美元 / 百萬 token；https://api-docs.deepseek.com/quick_start/pricing（deepseek-flash）
    "offpeak": {"in": 0.15, "out": 0.6}, "peak": {"in": 0.3, "out": 1.2}}  # 輸入以「快取未命中」計（最貴）
ZH_TOK = (0.6, 0.9)    # 每個中文字的 token；官方 0.6（https://api-docs.deepseek.com/quick_start/token_usage），高值留餘裕
# RAGAS 0.4.4 每次呼叫的固定提示（英文指令＋範例＋JSON 結構）字元數，實測 to_string()：
OVERHEAD = {"statements": 2000, "verdicts": 3300, "relevancy": 2000}
EN_TOK = 0.3           # 每個英文字元的 token（同上網址）
# 輸出 token 範圍（假設，非量測）：生成答案、拆陳述、每題判定、每個產生的問題
OUT_TOK = {"answer": (100, 500), "statements": (100, 400), "verdicts": (150, 700), "relevancy": (30, 100)}
STRICTNESS = 3         # answer relevancy 每題呼叫 3 次（ragas 預設 strictness）


def estimate(questions, search_fn) -> dict:
    """依實際檢索結果估算：生成呼叫數、評審呼叫數、token 範圍、費用範圍（美元）。"""
    n_gen = n_gate = n_judged = 0
    ctx_chars = q_chars = 0
    for q in questions:
        hits = search_fn(q["question"])
        if not hits:
            n_gate += 1
            continue
        n_gen += 1
        ctx_chars += sum(len(h["text"]) + len(h["company"]) + len(h["heading_path"]) for h in hits)
        q_chars += len(q["question"])
        n_judged += q["answerable"]
    lo_z, hi_z = ZH_TOK
    sys_chars = len(SYSTEM)
    # 生成：輸入 = 系統提示＋問題＋段落
    gen_in = (n_gen * sys_chars + q_chars + ctx_chars)
    # 評審：每題 faithfulness 2 次（拆陳述、判定）＋ answer relevancy 3 次。以最長答案 500 token 估答案中文字數
    ans_chars_hi, ans_chars_lo = 500 / lo_z, 100 / hi_z
    j_in_lo = n_judged * (OVERHEAD["statements"] + OVERHEAD["verdicts"] + STRICTNESS * OVERHEAD["relevancy"]) * EN_TOK * 0.8
    j_in_hi = n_judged * (OVERHEAD["statements"] + OVERHEAD["verdicts"] + STRICTNESS * OVERHEAD["relevancy"]) * EN_TOK * 1.2
    per_q_zh = lambda ans, ctx: (q_chars / max(n_gen, 1)) + 2 * ans + ctx  # 問題、答案（出現在拆陳述＋判定）、段落（判定）
    j_zh_lo = n_judged * (per_q_zh(ans_chars_lo, ctx_chars / max(n_gen, 1)) + STRICTNESS * ans_chars_lo) * lo_z
    j_zh_hi = n_judged * (per_q_zh(ans_chars_hi, ctx_chars / max(n_gen, 1)) + STRICTNESS * ans_chars_hi) * hi_z
    tok_in = (round(gen_in * lo_z + n_gen * 0 + j_in_lo + j_zh_lo), round(gen_in * hi_z + j_in_hi + j_zh_hi))
    o = OUT_TOK
    tok_out = (n_gen * o["answer"][0] + n_judged * (o["statements"][0] + o["verdicts"][0] + STRICTNESS * o["relevancy"][0]),
               n_gen * o["answer"][1] + n_judged * (o["statements"][1] + o["verdicts"][1] + STRICTNESS * o["relevancy"][1]))
    cost = lambda p, i, ou: (i * p["in"] + ou * p["out"]) / 1e6
    return {"questions": len(questions), "gated": n_gate, "generation_calls": n_gen,
            "judge_calls": n_judged * (2 + STRICTNESS), "judged_questions": n_judged,
            "tokens_in": tok_in, "tokens_out": tok_out,
            "cost_usd": (cost(PRICE["offpeak"], tok_in[0], tok_out[0]), cost(PRICE["peak"], tok_in[1], tok_out[1]))}


def format_estimate(e: dict) -> str:
    lo, hi = e["cost_usd"]
    return "\n".join([
        "## 乾跑估算（沒有呼叫任何 API）",
        f"題數 {e['questions']}；檢索被查無門檻擋住 {e['gated']} 題（不呼叫 LLM）；其餘 {e['generation_calls']} 題生成答案。",
        f"生成呼叫：{e['generation_calls']} 次（每題 1 次）。",
        f"評審呼叫（RAGAS 0.4.4，每題：faithfulness 2 次＋answer relevancy {STRICTNESS} 次）："
        f"{e['judged_questions']} 題 × {2 + STRICTNESS} = {e['judge_calls']} 次，上限（假設每題生成都不回查無；"
        "評審端 instructor 格式不符會自動重試，實際可能略多）。answer relevancy 另需 bge-m3 嵌入（本機，不花錢）。",
        f"總呼叫數 約 {e['generation_calls'] + e['judge_calls']} 次。",
        f"token 粗估：輸入 {e['tokens_in'][0]:,}–{e['tokens_in'][1]:,}；輸出 {e['tokens_out'][0]:,}–{e['tokens_out'][1]:,}"
        "（中文字以 0.6–0.9 token 估、RAGAS 固定提示依實測字元數估、輸出長度是假設，不是量測）。",
        f"費用粗估：US$ {lo:.3f}–{hi:.3f}（deepseek-flash；下限＝離峰價、上限＝尖峰價；輸入全以快取未命中計）。",
        "價目：輸入（未命中）離峰 $0.15／尖峰 $0.3，輸出離峰 $0.6／尖峰 $1.2，每百萬 token；"
        "尖峰＝UTC 01:00–04:00、06:00–10:00 週一至週五。來源 https://api-docs.deepseek.com/quick_start/pricing",
    ])


def main():
    import argparse
    import json
    from pathlib import Path
    from . import search
    from .evalset import questions_path
    ap = argparse.ArgumentParser(description="生成層評估。預設是乾跑（不打 API）；--run 才會呼叫 DeepSeek 並花錢。")
    ap.add_argument("--questions", default=str(questions_path()))
    ap.add_argument("--run", action="store_true", help="正式執行：呼叫 DeepSeek 生成與評審")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--review-out", default=REVIEW_OUT)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    qs = json.loads(Path(a.questions).read_text(encoding="utf-8"))["questions"]
    find = lambda q: search(q)  # 預設方式（bge-m3）、k=DEFAULT_K、套查無門檻
    if not a.run:
        text = format_estimate(estimate(qs, find))
        Path("eval/estimate_generation.txt").write_text(text + "\n", encoding="utf-8")
        print(text)
        return
    from .answer import answer
    from .ragas_judge import make_scorer
    rows = run_eval(qs, find, lambda q, h: answer(q, h), make_scorer())
    text = format_report(rows)
    Path(a.out).write_text(text + "\n", encoding="utf-8")
    Path(a.review_out).write_text(format_review(review_sample(rows, 10, a.seed)), encoding="utf-8-sig")
    Path(a.out).with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

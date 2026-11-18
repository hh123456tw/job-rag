"""跨公司驗證題（eval/questions_cross_val.json）：量「最後的答案」。python -X utf8 eval/run_cross_val.py score|report
每題照網站的跨公司路徑走一次：檢索 → 查無門檻 → DeepSeek 逐家整理 → 引用編號檢查；被擋住或失敗的題，答案算「沒有講到任何公司」。
兩種挑段方式各跑一次：hybrid（網站現行，BM25＋bge-m3）與 bge-m3（對照，只用向量挑段；門檻與其餘流程相同）。
評分：請 Sonnet 5.5（claude -p）讀答案，列出「答案說符合」的公司，再和題檔的符合公司名單比：
  找全＝該講到的公司裡講到幾家（加總）；講對＝答案說符合的公司裡真的符合幾家（加總）。
  不可回答題：被擋住，或答案沒有說任何一家符合，算拒答。
另記檢索層：每家符合的公司，取回的段落裡有沒有含證據引文的那一段。
每題跑完就存 dist/logs/cross_val_progress.json（中斷可續跑；已有結果的不重跑）。只跑一次、只量不調。
score 會呼叫真的 DeepSeek（每題每種挑段一次）與 Sonnet。寫 eval/results_cross_val.json／.txt。需要 JOB_RAG_CORPUS、JOB_RAG_MODELS、DeepSeek 金鑰。"""
import datetime
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402
from job_rag import retrieval as R  # noqa: E402
from job_rag.answer import AnswerError, answer  # noqa: E402
from job_rag.evaluate import questions_digest  # noqa: E402

QFILE = ROOT / "eval/questions_cross_val.json"
PROG = ROOT / "dist/logs/cross_val_progress.json"
OUT = ROOT / "eval/results_cross_val"
MODES = ("hybrid", "bge-m3")
SONNET = "claude-sonnet-5-5"
SYS = "You are one step of an automated grading program. Output only the JSON the task asks for. No markdown fences, no other text."


def vec_hits(q):
    """對照用：每家只用 bge-m3 挑 PER_COMPANY 段（其餘與 retrieval.cross_search 相同：分數、top、排序）。"""
    root = R._root(None, "demo")
    live = {n for _, n in app._company_buttons()}
    pool, ranked = R._rank_vector(root, "bge-m3", q, None)
    ok = lambda i: pool[i]["company"] != R.GENERAL and pool[i]["company"] in live
    top = max((sc for i, sc in ranked if ok(i)), default=0.0)
    taken, rows = {}, []
    for i, sc in ranked:
        c = pool[i]["company"]
        if ok(i) and taken.get(c, 0) < R.PER_COMPANY:
            taken[c] = taken.get(c, 0) + 1
            rows.append((i, sc))
    return [{k: pool[i][k] for k in ("company", "file", "heading_path", "text")} | {"score": float(sc), "top": float(top)} for i, sc in rows]


def said_yes(question, text, names):
    """請 Sonnet 5.5 列出答案說「符合」的公司。回公司名清單；評審出錯丟例外（不補結果）。"""
    prompt = ("下面是一個問題，和一個系統給的答案。請列出答案明確說「符合這個問題」的公司。\n"
              "規則：答案對某家公司寫「資料沒寫」「資料中沒有提到」「沒有」「查無」，或只說了和問題無關的事，都不算符合。"
              "只看答案怎麼說，不要用你自己的知識判斷對不對。公司名只能從這份清單選：" + "、".join(names) + "\n"
              '只輸出 JSON：{"yes": ["公司名", ...]}（沒有就輸出 {"yes": []}）\n\n'
              f"問題：{question}\n\n答案：\n{text}")
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["claude", "-p", "--model", SONNET, "--safe-mode", "--system-prompt", SYS, "--tools", "", "--strict-mcp-config",
                            "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"],
                           input=prompt.encode("utf-8"), capture_output=True, shell=True, timeout=600, cwd=d)
    env = json.loads(r.stdout.decode("utf-8"))
    if env.get("is_error") or list(env.get("modelUsage") or {SONNET: 0}) != [SONNET]:
        raise RuntimeError("評審出錯，或不是指定的模型")
    t = env["result"]
    yes = json.loads(t[t.index("{"):t.rindex("}") + 1])["yes"]
    return [c for c in names if c in yes]


def one(q, mode, names):
    hits = app._cross_hits(q["question"], "demo") if mode == "hybrid" else vec_hits(q["question"])
    row = {"low": app._low_cross(hits), "top": hits[0]["top"] if hits else None, "answer": None, "error": None, "yes": [],
           "retrieved": sorted({g["company"] for g in q.get("gold", []) if any(h["company"] == g["company"] and g["quote"] in h["text"] for h in hits)})}
    if row["low"]:
        return row
    try:
        row["answer"] = answer(q["question"], hits, cross=True)["answer"]
    except AnswerError as e:  # 引用編號檢查擋下、或 DeepSeek 失敗：照實記，答案當作沒有
        row["error"] = str(e)[:200]
        return row
    row["yes"] = said_yes(q["question"], row["answer"], names)
    return row


def score():
    qs = json.loads(QFILE.read_text(encoding="utf-8"))["questions"]
    names = [n for _, n in app._company_buttons()]
    prog = json.loads(PROG.read_text(encoding="utf-8")) if PROG.exists() else {}
    PROG.parent.mkdir(parents=True, exist_ok=True)
    for q in qs:
        for m in MODES:
            k = f"{m}:{q['id']}"
            if k in prog:
                continue
            prog[k] = one(q, m, names)
            PROG.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
            print(k, "擋住" if prog[k]["low"] else (prog[k]["error"] or prog[k]["yes"]), flush=True)


def mrr(qs):
    """檢索層的 MRR（不呼叫 LLM）：每一家符合的公司，含證據引文的那一段在那一家裡排第幾名，取倒數後平均（只看前 DEPTH 名）。
    只認題檔列的那一筆證據，別的段落也能支持時會低估。回 {挑段方式: {"mrr", "first", "pairs"}}。"""
    from job_rag.evaluate import DEPTH
    root = R._root(None, "demo")
    rr = {m: [] for m in MODES}
    for q in qs:
        pool, rv = R._rank_vector(root, "bge-m3", q["question"], None)
        _, rb = R._rank_bm25(root, q["question"], None)
        orders = {"bge-m3": [i for i, _ in rv], "hybrid": [i for i, _ in R.rrf([[i for i, _ in rb], [i for i, _ in rv]])]}
        for g in q["gold"]:
            for m, order in orders.items():
                mine = [i for i in order if pool[i]["company"] == g["company"]][:DEPTH]
                r = next((n for n, i in enumerate(mine, 1) if g["quote"] in pool[i]["text"]), None)
                rr[m].append(1 / r if r else 0.0)
    return {m: {"mrr": sum(v) / len(v), "first": sum(x == 1.0 for x in v), "pairs": len(v)} for m, v in rr.items()}


def report():
    qs = json.loads(QFILE.read_text(encoding="utf-8"))["questions"]
    prog = json.loads(PROG.read_text(encoding="utf-8"))
    ans, un = [q for q in qs if q["answerable"]], [q for q in qs if not q["answerable"]]
    out = {"date": datetime.date.today().isoformat(), "digest": questions_digest(qs), "n": len(qs), "n_answerable": len(ans), "n_unanswerable": len(un),
           "cross_floor": R.CROSS_FLOOR, "per_company": R.PER_COMPANY, "judge": "Claude Sonnet 5.5（claude -p）",
           "generator": "DeepSeek", "modes": {}, "rows": []}
    for m in MODES:
        want = found = said = retrieved = 0
        blocked = errors = 0
        for q in ans:
            r, g = prog[f"{m}:{q['id']}"], set(q["companies"])
            want += len(g)
            found += len(g & set(r["yes"]))
            said += len(r["yes"])
            retrieved += len(set(r["retrieved"]) & g)
            blocked += r["low"]
            errors += bool(r["error"])
        refused = sum(prog[f"{m}:{q['id']}"]["low"] or not prog[f"{m}:{q['id']}"]["yes"] for q in un)
        out["modes"][m] = {"want": want, "found": found, "said": said, "retrieved": retrieved, "blocked": blocked, "errors": errors,
                           "refused": refused, "by_kind": {}}
        for k in sorted({q["kind"] for q in ans}):
            sub = [q for q in ans if q["kind"] == k]
            out["modes"][m]["by_kind"][k] = {"n": len(sub), "want": sum(len(q["companies"]) for q in sub),
                                             "found": sum(len(set(q["companies"]) & set(prog[f"{m}:{q['id']}"]["yes"])) for q in sub)}
    for m, v in mrr(ans).items():
        out["modes"][m] |= {"mrr": v["mrr"], "first": v["first"]}
    for q in qs:
        out["rows"].append({"id": q["id"], "kind": q["kind"], "question": q["question"], "companies": q["companies"],
                            **{m: {k: prog[f"{m}:{q['id']}"][k] for k in ("low", "top", "yes", "retrieved", "error", "answer")} for m in MODES}})
    OUT.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    name = {"hybrid": "混合（BM25＋bge-m3，網站現行）", "bge-m3": "只用 bge-m3 挑段（對照）"}
    L = [f"跨公司驗證題：量最後的答案。題檔 eval/questions_cross_val.json（{out['n']} 題；摘要 {out['digest'][:16]}）；量測日期 {out['date']}。",
         "題目由 Codex CLI 的 GPT 出（直白口吻、題型事先定好），出完只跑這一次，沒有用來調任何參數。生成 DeepSeek；評審 Sonnet 5.5 只負責讀出「答案說哪幾家符合」。",
         f"門檻 CROSS_FLOOR = {out['cross_floor']}；每家取 {out['per_company']} 段。被門檻擋住或生成失敗的題，答案算沒有講到任何公司。", "",
         f"== 有答案 {out['n_answerable']} 題 ==", "挑段方式　找全（該講到的公司講到幾家）　講對（說符合的公司裡真的符合幾家）　檢索取到證據段　檢索 MRR　被門檻擋住　生成失敗"]
    for m, v in out["modes"].items():
        L.append(f"{name[m]}　{v['found']}/{v['want']}　{v['found']}/{v['said']}　{v['retrieved']}/{v['want']}　{v['mrr']:.3f}　{v['blocked']}/{out['n_answerable']} 題　{v['errors']} 題")
    L += ["", "== 分題型：找全 =="]
    for k in out["modes"]["hybrid"]["by_kind"]:
        a, b = out["modes"]["hybrid"]["by_kind"][k], out["modes"]["bge-m3"]["by_kind"][k]
        L.append(f"{k}（{a['n']} 題）　混合 {a['found']}/{a['want']}　只用 bge-m3 {b['found']}/{b['want']}")
    L += ["", f"== 不可回答 {out['n_unanswerable']} 題：拒答（被擋住，或答案沒有說任何一家符合）=="]
    for m, v in out["modes"].items():
        L.append(f"{name[m]}　{v['refused']}/{out['n_unanswerable']}")
    L += ["", "題號 題型 符合家數 混合:擋/講到/多講 bge-m3:擋/講到/多講 問句"]
    for r in out["rows"]:
        g = set(r["companies"])
        cell = lambda x: f"{'擋' if x['low'] else '-'}/{len(g & set(x['yes']))}/{len(set(x['yes']) - g)}"
        L.append(f"{r['id']} {r['kind']} {len(g)} {cell(r['hybrid'])} {cell(r['bge-m3'])} {r['question']}")
    L += ["", "== 限制 ==",
          "單一模型出題；「符合的公司有沒有列全」只有出題模型自己掃語料的保證，沒有人工確認，所以「講對」可能把其實符合、但名單漏掉的公司算成講錯。"
          "DeepSeek 與評審都只跑一次，輸出有隨機性。題數少。檢索層的「取到證據段」只認題檔列的那一筆證據，別的段落也能支持時會低估。"]
    OUT.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:16]))


if __name__ == "__main__":
    {"score": score, "report": report}[sys.argv[1]]()

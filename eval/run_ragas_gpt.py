"""RAGAS 換評審：用另一個模型（不是生成用的 DeepSeek）重評已存的答案。檔名沿用 gpt，評審可選：
  --judge sonnet（預設）：Claude Sonnet 5.5，經 Claude Code CLI `claude -p --model claude-sonnet-5-5`（用登入的訂閱，不需要 API 金鑰）
  --judge codex：Codex CLI 預設 GPT 模型 `codex exec -s read-only`
  .venv-ragas/Scripts/python -X utf8 eval/run_ragas_gpt.py score [--judge sonnet] [--limit N] [--workers N]
  .venv-ragas/Scripts/python -X utf8 eval/run_ragas_gpt.py report [--judge sonnet]
做法：在本機開一個 OpenAI 相容的轉接（只聽 127.0.0.1），RAGAS 每次要評審就由它呼叫上面的指令列工具。
答案與段落不重新產生：30 題組取 eval/results_generation.json 已評分的題，獨立題取 eval/results_heldout_answers_v2.json 可評的題
（與 DeepSeek 評審那次是同一批答案、同一批段落）。嵌入仍用本機 bge-m3。
每題評完就存 dist/logs/ragas_<judge>_progress.json，可中斷續跑；失敗的題記錄錯誤，不補分。
輸出 eval/results_ragas_<judge>.json／.txt（codex 的檔名是 gpt）。模型單次輸出有隨機性，只跑一次。"""
import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
JUDGES = {  # 名稱 -> (檔名用的字, 頁面上的短名, 報告上的全名)
    "sonnet": ("sonnet", "Sonnet 5.5", "Claude Sonnet 5.5（claude -p --model claude-sonnet-5-5，Claude Code CLI）"),
    "codex": ("gpt", "GPT", "Codex CLI 預設 GPT 模型（codex exec -s read-only）"),
}
JUDGE = "sonnet"  # main() 依 --judge 設定
SONNET = "claude-sonnet-5-5"
SYS = "You are one step of an automated grading program. Output only the single JSON object the task asks for. No markdown fences, no other text."


def prog_file():
    return ROOT / f"dist/logs/ragas_{JUDGES[JUDGE][0]}_progress.json"


def out_file():
    return ROOT / f"eval/results_ragas_{JUDGES[JUDGE][0]}"
METRICS = ("faithfulness", "answer_relevancy")
NOT_FOUND = "查無"
RETRY = 2
TAIL = ("\n\n以上是完整的任務。只輸出一個符合要求的 JSON 物件：不要 markdown 圍欄、不要任何說明文字。"
        "不要讀寫檔案、不要執行指令、不要上網；只根據上面的文字作答。")


def items():
    """(題組, 題號, 問句, 答案, 段落)。與 DeepSeek 評審那次用同一批。"""
    out = []
    for r in json.loads((ROOT / "eval/results_generation.json").read_text(encoding="utf-8")):
        if r["status"] == "已評分":
            out.append(("tune", r["id"], r["question"], r["answer"], r["contexts"]))
    for r in json.loads((ROOT / "eval/results_heldout_answers_v2.json").read_text(encoding="utf-8"))["rows"]:
        if r["answerable"] and r["answer_status"] == "ok" and r["answer"].strip() != NOT_FOUND and r["contexts"]:
            out.append(("held", r["id"], r["question"], r["answer"], r["contexts"]))
    return out


def codex(prompt: str) -> str:
    """呼叫一次 Codex CLI，回它的最後訊息（必須是 JSON 物件）；不是就重試，仍不行丟例外。"""
    for _ in range(RETRY + 1):
        with tempfile.TemporaryDirectory() as d:
            of = Path(d) / "out.txt"
            subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-C", d, "-o", str(of), "-"],
                           input=prompt.encode("utf-8"), capture_output=True, shell=True, timeout=900)
            try:
                t = re.sub(r"^```(?:json)?\s*|\s*```$", "", of.read_text(encoding="utf-8").strip())
                t = t[t.index("{"):t.rindex("}") + 1]
                json.loads(t)
                return t
            except (OSError, ValueError):
                continue
    raise RuntimeError("Codex 沒有回合法的 JSON")


def sonnet(prompt: str) -> str:
    """呼叫一次 Claude Sonnet 5.5（Claude Code CLI，乾淨模式：不載入專案指示、掛鉤、工具、MCP）。回 JSON 物件字串；不是就重試。"""
    last = ""
    for _ in range(RETRY + 1):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(["claude", "-p", "--model", SONNET, "--safe-mode", "--system-prompt", SYS, "--tools", "", "--strict-mcp-config",
                                "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"],
                               input=prompt.encode("utf-8"), capture_output=True, shell=True, timeout=900, cwd=d)
            try:
                env = json.loads(r.stdout.decode("utf-8"))
                if env.get("is_error") or list(env.get("modelUsage") or {SONNET: 0}) != [SONNET]:
                    last = str(env.get("result"))[:200]
                    continue  # 出錯，或不是指定的模型：不採用
                t = re.sub(r"^```(?:json)?\s*|\s*```$", "", env["result"].strip())
                t = t[t.index("{"):t.rindex("}") + 1]
                json.loads(t)
                return t
            except (ValueError, KeyError, AttributeError) as e:
                last = f"{type(e).__name__}: {r.stdout[:200]!r} {r.stderr[:200]!r}"
    raise RuntimeError(f"Sonnet 沒有回合法的 JSON：{last}")


class Shim(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        prompt = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in body["messages"]) + TAIL
        try:
            content, code = (sonnet if JUDGE == "sonnet" else codex)(prompt), 200
        except Exception as e:  # noqa: BLE001  失敗照實回 500，評分端記成錯誤
            content, code = str(e), 500
        if code == 200:
            data = {"id": "codex", "object": "chat.completion", "created": int(time.time()), "model": "codex-cli-gpt",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
        else:
            data = {"error": {"message": content, "type": "codex_error"}}
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def score(a):
    from job_rag import ragas_judge
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Shim)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    lock, elock = threading.Lock(), threading.Lock()

    def embed(texts):  # 多執行緒共用一個本機模型：一次只讓一個人編碼
        with elock:
            return ragas_judge._embed_fn(texts)

    PROG = prog_file()
    prog = json.loads(PROG.read_text(encoding="utf-8")) if PROG.exists() else {"rows": {}}
    PROG.parent.mkdir(parents=True, exist_ok=True)
    todo = [x for x in items() if not all(isinstance(prog["rows"].get(f"{x[0]}:{x[1]}", {}).get(m), (int, float)) for m in METRICS)]
    todo = todo[:a.limit] if a.limit else todo
    print("要評", len(todo), "題；轉接", base, flush=True)

    def one(x):
        s, i, q, ans, ctx = x
        cur = dict(prog["rows"].get(f"{s}:{i}", {}))
        need = tuple(m for m in METRICS if not isinstance(cur.get(m), (int, float)))
        try:
            cur.update(ragas_judge.make_scorer(base_url=base, embed_fn=embed, metrics=need, api_key="local", model="codex-cli-gpt", timeout=1800)(q, ans, ctx))
            cur.pop("error", None)
        except Exception as e:  # noqa: BLE001  失敗就記錄，不補分
            cur["error"] = f"{type(e).__name__}: {e}"[:300]
        with lock:
            prog["rows"][f"{s}:{i}"] = cur
            PROG.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
        print(s, i, cur, flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, todo))


def _boot(xs, n=2000, seed=0):
    rng = random.Random(seed)
    m = sorted(sum(rng.choices(xs, k=len(xs))) / len(xs) for _ in range(n))
    return [m[int(n * 0.025)], m[int(n * 0.975) - 1]]


def report(a):
    PROG, OUT = prog_file(), out_file()
    prog = json.loads(PROG.read_text(encoding="utf-8"))["rows"] if PROG.exists() else {}
    old = {("tune", r["id"]): r for r in json.loads((ROOT / "eval/results_generation.json").read_text(encoding="utf-8"))}
    for r in json.loads((ROOT / "eval/results_heldout_generation.json").read_text(encoding="utf-8"))["per_question"]:
        old[("held", r["id"])] = r
    out = {"judge": JUDGES[JUDGE][2], "judge_short": JUDGES[JUDGE][1], "generator": "DeepSeek", "date": time.strftime("%Y-%m-%d"), "sets": {}, "per_question": []}
    for s in ("tune", "held"):
        xs = [x for x in items() if x[0] == s]
        st = {"n": len(xs), "failed": [i for _, i, *_ in xs if prog.get(f"{s}:{i}", {}).get("error")]}
        for m in METRICS:
            v = [prog[f"{s}:{i}"][m] for _, i, *_ in xs if isinstance(prog.get(f"{s}:{i}", {}).get(m), (int, float))]
            d = [old[(s, i)][m] for _, i, *_ in xs if isinstance(old.get((s, i), {}).get(m), (int, float))
                 and isinstance(prog.get(f"{s}:{i}", {}).get(m), (int, float))]  # 只比兩邊都有分數的題
            st[m] = {"n": len(v), "mean": sum(v) / len(v) if v else None, "ci95": _boot(v) if len(v) > 1 else None,
                     "deepseek_judge_mean": sum(d) / len(d) if d else None}
        out["sets"][s] = st
        for _, i, q, *_ in xs:
            p = prog.get(f"{s}:{i}", {})
            out["per_question"].append({"set": s, "id": i, "question": q, **{m: p.get(m) for m in METRICS}, "error": p.get("error")})
    out["note"] = (f"評審換成 {JUDGES[JUDGE][1]}，生成仍是 DeepSeek。答案與段落和 DeepSeek 評審那次相同，沒有重新生成；跨公司路徑 11/18 的改動（門檻、混合挑段）之後沒有重新生成答案。"
                   "RAGAS 的提示詞是英文、原封不動；評審單次輸出有隨機性，只跑一次。只量答案有沒有依據、有沒有答到問題，不量對不對。")
    OUT.with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    f = lambda x: "-" if x is None else f"{x:.3f}"
    name = {"tune": "30 題組", "held": "獨立測試題"}
    L = [f"RAGAS（評審：{out['judge']}；生成：DeepSeek）量測日期 {out['date']}", ""]
    for s, st in out["sets"].items():
        L.append(f"== {name[s]}：送評 {st['n']} 題；失敗 {len(st['failed'])} 題（{'、'.join(st['failed']) or '無'}）==")
        for m, lab in (("faithfulness", "忠實度"), ("answer_relevancy", "答案相關性")):
            v = st[m]
            L.append(f"{lab}：平均 {f(v['mean'])}（{v['n']} 題）" + (f"；95% 區間 {v['ci95'][0]:.3f}–{v['ci95'][1]:.3f}" if v["ci95"] else "")
                     + f"；同一批答案由 DeepSeek 評審時是 {f(v['deepseek_judge_mean'])}")
        L.append("")
    L += ["題組 題號 忠實度 答案相關性 備註"] + [f"{name[r['set']]} {r['id']} {f(r['faithfulness'])} {f(r['answer_relevancy'])} {r['error'] or ''}" for r in out["per_question"]]
    L += ["", "## 限制", out["note"]]
    OUT.with_suffix(".txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["score", "report"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--judge", choices=list(JUDGES), default="sonnet")
    a = ap.parse_args()
    JUDGE = a.judge
    {"score": score, "report": report}[a.phase](a)

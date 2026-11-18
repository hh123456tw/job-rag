"""逐句複查：python -X utf8 eval/crossjudge/run_judge.py build|judge|report [gpt|sonnet]
build   由 eval/results_generation.json（30 題組）與 eval/results_heldout_generation.json＋results_heldout_answers_v2.json（獨立題）
        取 RAGAS 已評分的題，寫 input_new.json、input_heldout.json（只含公開段落；被擋住或回「查無」的題不送）。
judge   每批 8 題交給評審，規則是 judge_prompt.md。評審（第二個參數，預設 gpt）：
        gpt     codex exec -s read-only（Codex CLI 預設 GPT 模型）；輸出 judge_gpt_new.json（同內容複製成 judge_gpt.json）、judge_gpt_heldout.json
        sonnet  claude -p --model claude-sonnet-5-5（Claude Code CLI，乾淨模式，不載入專案指示、掛鉤、工具）；輸出 judge_sonnet_new.json、judge_sonnet_heldout.json
        每批失敗最多重試 2 次；仍失敗的批次寫進 judge_failed.json（sonnet：judge_failed_sonnet.json），不補分。評審單次輸出有隨機性。
report  印各題組題數、陳述數、有支持數。"""
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
BATCH, RETRY, WORKERS = 8, 2, 4
JUDGE = sys.argv[2] if len(sys.argv) > 2 else "gpt"
SONNET = "claude-sonnet-5-5"
SYS = "You are one step of an automated grading program. Output only the JSON the task asks for. No markdown fences, no other text."


def build():
    g = [r for r in json.loads((ROOT / "eval/results_generation.json").read_text(encoding="utf-8")) if r["status"] == "已評分"]
    a = [{"id": r["id"], "question": r["question"], "answer": r["answer"], "passages": r["contexts"]} for r in g]
    h = json.loads((ROOT / "eval/results_heldout_generation.json").read_text(encoding="utf-8"))["per_question"]
    v2 = {r["id"]: r for r in json.loads((ROOT / "eval/results_heldout_answers_v2.json").read_text(encoding="utf-8"))["rows"]}
    b = [{"id": x["id"], "question": x["question"], "answer": x["answer"], "passages": v2[x["id"]]["contexts"]} for x in h]
    (HERE / "input_new.json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "input_heldout.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    print("題組", len(a), "獨立題", len(b))


def _ask(prompt: str, d: str) -> str:
    """把提示交給評審，回它的文字輸出。"""
    if JUDGE == "sonnet":
        r = subprocess.run(["claude", "-p", "--model", SONNET, "--safe-mode", "--system-prompt", SYS, "--tools", "", "--strict-mcp-config",
                            "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"],
                           input=prompt.encode("utf-8"), capture_output=True, shell=True, timeout=1500, cwd=d)
        env = json.loads(r.stdout.decode("utf-8"))
        if env.get("is_error") or list(env.get("modelUsage") or {SONNET: 0}) != [SONNET]:
            raise ValueError("評審出錯，或不是指定的模型")
        return env["result"]
    of = Path(d) / "out.txt"
    subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-C", d, "-o", str(of), "-"],
                   input=prompt.encode("utf-8"), capture_output=True, shell=True, timeout=1500)
    return of.read_text(encoding="utf-8")


def _run(batch, tag):
    prompt = (HERE / "judge_prompt.md").read_text(encoding="utf-8") + "\n\ninput.json：\n" + json.dumps(batch, ensure_ascii=False)
    for t in range(RETRY + 1):
        with tempfile.TemporaryDirectory() as d:
            try:
                txt = _ask(prompt, d).strip()
                rows = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
                if {r["id"] for r in rows} == {q["id"] for q in batch}:
                    return rows, t
            except (OSError, ValueError, KeyError, AttributeError):
                pass
        print(tag, "失敗，重試", t + 1, flush=True)
    return None, RETRY + 1


def judge():
    failed, retries = [], 0
    for src, out in (("input_new.json", f"judge_{JUDGE}_new.json"), ("input_heldout.json", f"judge_{JUDGE}_heldout.json")):
        qs = json.loads((HERE / src).read_text(encoding="utf-8"))
        batches = [qs[i:i + BATCH] for i in range(0, len(qs), BATCH)]
        with ThreadPoolExecutor(WORKERS) as ex:  # 批次之間互不相干，同時跑；結果照原順序接回
            done = list(ex.map(lambda x: _run(x[1], f"{src}#{x[0]}"), enumerate(batches)))
        rows = []
        for n, (b, (r, t)) in enumerate(zip(batches, done)):
            retries += min(t, RETRY)
            if r is None:
                failed.append({"src": src, "ids": [q["id"] for q in b]})
            else:
                rows += r
            print(src, n, "完成" if r else "失敗", flush=True)
        (HERE / out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if JUDGE == "gpt":
        shutil.copy(HERE / "judge_gpt_new.json", HERE / "judge_gpt.json")
    (HERE / ("judge_failed.json" if JUDGE == "gpt" else f"judge_failed_{JUDGE}.json")).write_text(
        json.dumps({"failed": failed, "retries": retries}, ensure_ascii=False, indent=1), encoding="utf-8")


def report():
    for f in (f"judge_{JUDGE}_new.json", f"judge_{JUDGE}_heldout.json"):
        rows = json.loads((HERE / f).read_text(encoding="utf-8"))
        cl = [c for r in rows for c in r["claims"]]
        print(f, "題", len(rows), "陳述", len(cl), "有支持", sum(bool(c["supported"]) for c in cl),
              "不支持", [(r["id"], c["text"], c["evidence"]) for r in rows for c in r["claims"] if not c["supported"]])


if __name__ == "__main__":
    {"build": build, "judge": judge, "report": report}[sys.argv[1]]()

"""GPT 複查：python -X utf8 eval/crossjudge/run_judge.py build|judge|report
build   由 eval/results_generation.json（30 題組）與 eval/results_heldout_generation.json＋results_heldout_answers_v2.json（獨立題）
        取 RAGAS 已評分的題，寫 input_new.json、input_heldout.json（只含公開段落；被擋住或回「查無」的題不送）。
judge   每批 8 題呼叫 codex exec -s read-only（預設 GPT 模型），規則是 judge_prompt.md；輸出 judge_gpt_new.json（同內容複製成 judge_gpt.json）、judge_gpt_heldout.json。
        每批失敗最多重試 2 次；仍失敗的批次寫進 judge_failed.json，不補分。GPT 單次輸出有隨機性。
report  印各題組題數、陳述數、有支持數。"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
BATCH, RETRY = 8, 2


def build():
    g = [r for r in json.loads((ROOT / "eval/results_generation.json").read_text(encoding="utf-8")) if r["status"] == "已評分"]
    a = [{"id": r["id"], "question": r["question"], "answer": r["answer"], "passages": r["contexts"]} for r in g]
    h = json.loads((ROOT / "eval/results_heldout_generation.json").read_text(encoding="utf-8"))["per_question"]
    v2 = {r["id"]: r for r in json.loads((ROOT / "eval/results_heldout_answers_v2.json").read_text(encoding="utf-8"))["rows"]}
    b = [{"id": x["id"], "question": x["question"], "answer": x["answer"], "passages": v2[x["id"]]["contexts"]} for x in h]
    (HERE / "input_new.json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "input_heldout.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    print("題組", len(a), "獨立題", len(b))


def _run(batch, tag):
    prompt = (HERE / "judge_prompt.md").read_text(encoding="utf-8") + "\n\ninput.json：\n" + json.dumps(batch, ensure_ascii=False)
    for t in range(RETRY + 1):
        with tempfile.TemporaryDirectory() as d:
            of = Path(d) / "out.txt"
            subprocess.run(["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-C", d, "-o", str(of), "-"],
                           input=prompt.encode("utf-8"), capture_output=True, shell=True, timeout=1500)
            try:
                txt = of.read_text(encoding="utf-8").strip()
                rows = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
                if {r["id"] for r in rows} == {q["id"] for q in batch}:
                    return rows, t
            except (OSError, ValueError, KeyError):
                pass
        print(tag, "失敗，重試", t + 1, flush=True)
    return None, RETRY + 1


def judge():
    failed, retries = [], 0
    for src, out in (("input_new.json", "judge_gpt_new.json"), ("input_heldout.json", "judge_gpt_heldout.json")):
        qs = json.loads((HERE / src).read_text(encoding="utf-8"))
        rows = []
        for i in range(0, len(qs), BATCH):
            b = qs[i:i + BATCH]
            r, t = _run(b, f"{src}#{i // BATCH}")
            retries += min(t, RETRY)
            if r is None:
                failed.append({"src": src, "ids": [q["id"] for q in b]})
            else:
                rows += r
            print(src, i // BATCH, "完成" if r else "失敗", flush=True)
        (HERE / out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy(HERE / "judge_gpt_new.json", HERE / "judge_gpt.json")
    (HERE / "judge_failed.json").write_text(json.dumps({"failed": failed, "retries": retries}, ensure_ascii=False, indent=1), encoding="utf-8")


def report():
    for f in ("judge_gpt_new.json", "judge_gpt_heldout.json"):
        rows = json.loads((HERE / f).read_text(encoding="utf-8"))
        cl = [c for r in rows for c in r["claims"]]
        print(f, "題", len(rows), "陳述", len(cl), "有支持", sum(bool(c["supported"]) for c in cl),
              "不支持", [(r["id"], c["text"], c["evidence"]) for r in rows for c in r["claims"] if not c["supported"]])


if __name__ == "__main__":
    {"build": build, "judge": judge, "report": report}[sys.argv[1]]()

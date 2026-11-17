"""端到端拒答（真 DeepSeek，只跑新版語料）。每題最多呼叫一次，不重試。
python -X utf8 eval_compare/run_e2e.py
流程同 eval/run_answers.py：/api/search（自動偵測公司）；沒被檢索門檻擋住才呼叫 /api/answer。用 Flask test client，不開埠。
金鑰從主專案 .env 讀進本程序環境變數，不印出、不寫檔。"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
for line in Path(r"C:\claude\aipe04期末\job-rag\.env").read_text(encoding="utf-8").splitlines():
    k, _, v = line.partition("=")
    if k.strip() == "DEEPSEEK_API_KEY":
        os.environ["DEEPSEEK_API_KEY"] = v.strip().strip("\"'")
import app  # noqa: E402

EXCLUDE = {"questions_heldout:h40", "questions_real:r20", "questions_cross:u03"}  # 新版已含答案或已含 Go 語言，不算無答案
rows = []
c = app.app.test_client()
calls = 0
for f in ("questions", "questions_heldout", "questions_real", "questions_cross"):
    for q in json.loads((ROOT / "eval" / f"{f}.json").read_bytes().decode("utf-8"))["questions"]:
        key = f"{f}:{q['id']}"
        if q["answerable"] or key in EXCLUDE:
            continue
        s = c.get("/api/search", query_string={"q": q["question"], "company": q.get("company") or ""}).get_json()
        row = {"key": key, "question": q["question"], "search_status": s.get("status"), "company": s.get("company"), "cross": s.get("cross"),
               "top": max((h.get("score", 0) for h in s.get("hits", [])), default=None), "threshold": s.get("threshold"),
               "answer_status": None, "answer": None}
        if s.get("status") == "ok":
            time.sleep(1)
            calls += 1
            r = c.get("/api/answer", query_string={"q": q["question"], "company": s.get("company") or ""}).get_json()
            row["answer_status"], row["answer"] = r.get("status"), r.get("answer") or r.get("message")
        rows.append(row)
        print(key, row["search_status"], row["answer_status"], (row["answer"] or "")[:40].replace("\n", " "), flush=True)
(HERE / "res_e2e_new.json").write_text(json.dumps({"deepseek_calls": calls, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
print("題數", len(rows), "DeepSeek 呼叫", calls)

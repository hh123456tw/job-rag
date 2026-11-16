"""票 38：對三份題組每題實跑主服務，記下實際答案：python -X utf8 eval/run_answers.py [--base URL] [--max-calls 80]
流程與網站相同：先 /api/search（會自動偵測公司），沒被檢索擋住才用偵測到的公司呼叫 /api/answer（真 DeepSeek）。
寫入 eval/results_answers.json（每題寫完就存，可中斷後續跑）。不改答案、不重試；失敗就記失敗；遇到每小時上限（status=limit）就停止。
DeepSeek 呼叫上限預設 80，每次呼叫間隔 ≥ 1 秒。存取碼不寫入任何檔案；本機直連不需要。"""
import argparse
import datetime
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "eval" / "results_answers.json"
SETS = ("questions", "questions_real", "questions_cross")


def get(base, path, **q):
    url = f"{base}{path}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except ValueError:
            return e.code, {"status": "error", "message": f"HTTP {e.code}"}
    except (OSError, ValueError) as e:
        return 0, {"status": "error", "message": f"連線失敗：{e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5000")
    ap.add_argument("--max-calls", type=int, default=80)
    a = ap.parse_args()
    done, before = {}, 0
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        before = old.get("deepseek_calls", 0)
        done = {r["id"]: r for r in old["rows"] if r["answer_status"] != "limit"}
    calls, stopped = 0, None
    for name in SETS:
        for q in json.loads((ROOT / "eval" / f"{name}.json").read_text(encoding="utf-8"))["questions"]:
            if q["id"] in done:
                continue
            if stopped or calls >= a.max_calls:
                stopped = stopped or "max_calls"
                break
            time.sleep(1)
            _, s = get(a.base, "/api/search", q=q["question"], company=q.get("company", ""))
            row = {"id": q["id"], "set": name, "question": q["question"], "company": q.get("company") or None, "answerable": q["answerable"],
                   "top_score": max((h["score"] for h in s.get("hits", []) if "score" in h), default=None),
                   "threshold_used": s.get("threshold"), "search_status": s.get("status"), "detected_company": s.get("company") or None,
                   "cross": s.get("cross"), "answer": None, "answer_status": None, "sources": [],
                   "date": datetime.date.today().isoformat(), "run": 1}
            if s.get("status") == "ok":
                time.sleep(1)
                calls += 1
                code, r = get(a.base, "/api/answer", q=q["question"], company=s.get("company") or "")
                row["answer_status"] = r.get("status")
                row["answer"] = r.get("answer")
                row["sources"] = [{"company": x.get("company"), "title": x.get("heading_path")} for x in r.get("sources", [])]
                if r.get("status") != "ok":
                    row["error"] = r.get("message")
                if r.get("status") == "limit" or code == 429:
                    stopped = "limit"
            else:
                row["answer_status"] = "skipped_low" if s.get("status") == "low" else "skipped_error"
                if s.get("status") != "low":
                    row["error"] = s.get("message")
            done[q["id"]] = row
            OUT.write_text(json.dumps({"note": "單次執行；答案由 DeepSeek 產生，可能隨機。", "deepseek_calls": before + calls,
                                       "rows": list(done.values())}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(row["id"], row["search_status"], row["answer_status"], flush=True)
        if stopped:
            break
    print("完成題數", len(done), "本次 DeepSeek 呼叫", calls, "停止原因", stopped)


if __name__ == "__main__":
    sys.exit(main())

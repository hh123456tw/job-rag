"""由 results_answers.json 彙整端到端拒答：python -X utf8 eval/make_endtoend.py
範圍：questions.json 與 questions_real.json 裡「語料沒有答案」的題（跨公司題組另算）。拒答＝答案恰為「查無」，或被檢索門檻擋下（skipped_low）。
只彙整、不重跑；答案必須已由 run_answers.py 實跑。"""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
rows = [r for r in json.loads((ROOT / "eval/results_answers.json").read_text(encoding="utf-8"))["rows"]
        if r["set"] in ("questions", "questions_real") and not r["answerable"]]
out = [{"id": r["id"], "top_score": r["top_score"], "search_status": r["search_status"], "answer": r["answer"] or "",
        "refused": r["answer_status"] == "skipped_low" or (r["answer_status"] == "ok" and (r["answer"] or "").strip() == "查無")} for r in rows]
gate = sum(r["answer_status"] == "skipped_low" for r in rows)
ref = sum(o["refused"] for o in out)
ids = "、".join(o["id"] for o in out)
d = {"date": datetime.date.today().isoformat(), "method": "真 DeepSeek；網站實際路徑 /api/search + /api/answer（補職稱清單後的語料）",
     "note": f"{len(out)} 題；同一人出題；只跑一次；拒答＝答案為查無或被檢索門檻擋下", "n": len(out), "refused": ref,
     "by_gate": gate, "by_answer_layer": ref - gate, "rows": out}
(ROOT / "eval/results_endtoend.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
leak = [o["id"] for o in out if not o["refused"]]
txt = (f"端到端拒答檢查（檢索門檻＋答案層，真 DeepSeek）。{d['date']}，補職稱清單後的語料，隨 eval/run_answers.py 實跑一次（網站 /api/search 與 /api/answer）。\n"
       f"做法：eval 的 {len(out)} 題「語料沒有答案」（{ids}），照網站實際路徑呼叫。\n"
       f"結果：{ref}/{len(out)} 拒答（{ref - gate} 題由答案層回「查無」，{gate} 題被檢索門檻擋下）。" + (f"沒拒答：{'、'.join(leak)}。" if leak else "") + "逐題見 results_endtoend.json。\n"
       "讀法：0.62 的檢索門檻單獨只擋住很少不可回答題；真正把關的是第二層（答案層「沒寫就回查無」）。\n"
       f"限制：{len(out)} 題、同一人出題、只跑一次（DeepSeek 輸出可能隨機）；「拒答」以答案為「查無」或 low 判定；沒有人工逐字核對。\n")
(ROOT / "eval/results_endtoend.txt").write_text(txt, encoding="utf-8")
print(txt)

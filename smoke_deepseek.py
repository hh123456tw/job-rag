"""手動冒煙：讀 .env 的 DEEPSEEK_API_KEY，問一題，印出答案。會呼叫真 API（花一點錢）。
用法：python -X utf8 smoke_deepseek.py "問題"   （需設 JOB_RAG_CORPUS）"""
import sys

from job_rag import search
from job_rag.answer import AnswerError, answer

q = sys.argv[1] if len(sys.argv) > 1 else "這家公司做什麼？"
try:
    r = answer(q, search(q))
except (AnswerError, RuntimeError) as e:
    sys.exit(f"失敗：{e}")
print(r["answer"])
for s in r["sources"]:
    print("-", s["company"], s["file"], s["heading_path"])

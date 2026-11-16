"""求職情報問答（Flask 單頁）。python -X utf8 app.py"""
from flask import Flask, request
from markupsafe import escape

from job_rag import search
from job_rag.answer import AnswerError, _post, answer

app = Flask(__name__)


@app.get("/")
def index():
    q = request.args.get("q", "").strip()
    company = request.args.get("company", "").strip() or None
    body, err, ans = "", "", ""
    if q:
        try:
            hits = search(q, company=company)
            body = "".join(
                f"<div class='hit'><b>{escape(h['company'])}</b> · {escape(h['file'])} · "
                f"{escape(h['heading_path'])}<pre>{escape(h['text'])}</pre></div>"
                for h in hits
            ) or "<p>沒有符合的段落。</p>"
            if hits:  # 沒有原文結果就沒有可整理的內容
                if request.args.get("answer"):
                    try:
                        r = answer(q, hits, post=_post)
                        src = "".join(f"<li>{escape(s['company'])} · {escape(s['file'])} · {escape(s['heading_path'])}</li>" for s in r["sources"])
                        ans = f"<div class='ans'><b>答案</b><pre>{escape(r['answer'])}</pre><ul>{src}</ul></div>"
                    except AnswerError as e:
                        ans = f"<p style='color:#c00'>整理失敗：{escape(e)}（原文結果不受影響）</p>"
                else:
                    ans = "<button name=answer value=1 form=f>整理成答案</button>"
        except RuntimeError as e:
            err = f"<p style='color:#c00'>錯誤：{escape(e)}</p>"
    return f"""<!doctype html><meta charset=utf-8><title>求職情報問答</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:auto}}.hit{{border:1px solid #ccc;padding:8px;margin:8px 0}}
.ans{{background:#f3f8ff;padding:8px}}pre{{white-space:pre-wrap}}</style>
<h1>求職情報問答</h1>
<form id=f><input name=q value="{escape(q)}" size=40 placeholder="輸入問題"> 公司：<input name=company value="{escape(company or '')}" size=10> <button>查</button></form>
{err}{body}{ans}"""


if __name__ == "__main__":
    app.run(port=5000)

"""求職情報問答（Flask 單頁）。python -X utf8 app.py"""
from flask import Flask, request
from markupsafe import escape

from job_rag import search

app = Flask(__name__)
ORANGE = "#e8710a"


@app.get("/")
def index():
    q = request.args.get("q", "").strip()
    company = request.args.get("company", "").strip() or None
    mode = "query" if request.args.get("mode") == "query" else "demo"
    body, err = "", ""
    if q:
        try:
            hits = search(q, mode=mode, company=company)
            body = "".join(
                f"<div class='hit{' priv' if h['private'] else ''}'><b>{escape(h['company'])}</b> · {escape(h['file'])} · "
                f"{escape(h['heading_path'])}{' · 私人' if h['private'] else ''}<pre>{escape(h['text'])}</pre></div>"
                for h in hits
            ) or "<p>沒有符合的段落。</p>"
        except RuntimeError as e:
            err = f"<p style='color:#c00'>錯誤：{escape(e)}</p>"
    banner = f"<div style='background:{ORANGE};color:#fff;padding:8px'>查詢模式：畫面含私人段落，請勿轉給別人看</div>" if mode == "query" else ""
    return f"""<!doctype html><meta charset=utf-8><title>求職情報問答</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:auto}}.hit{{border:1px solid #ccc;padding:8px;margin:8px 0}}
.priv{{border-color:{ORANGE}}}pre{{white-space:pre-wrap}}</style>{banner}
<h1>求職情報問答</h1>
<form><input name=q value="{escape(q)}" size=40 placeholder="輸入問題"> 公司：<input name=company value="{escape(company or '')}" size=10>
<label><input type=checkbox name=mode value=query {'checked' if mode == 'query' else ''}> 查詢模式</label> <button>查</button></form>
{err}{body}"""


if __name__ == "__main__":
    app.run(port=5000)

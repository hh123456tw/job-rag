"""求職情報問答（Flask 單頁）。python -X utf8 app.py"""
import json
from pathlib import Path

from flask import Flask, request
from markupsafe import escape

from job_rag import retrieval, search
from job_rag.answer import AnswerError, _post, answer
from job_rag.evaluate import DEPTH, hit_rank

app = Flask(__name__)

# (按鈕文字, 語料的公司欄位)。名稱以 public_company_counts() 為準，只有尼諾思不同。
LIVE_COMPANIES = [("台灣大哥大", "台灣大哥大"), ("聯合報", "聯合報"), ("叡揚資訊", "叡揚資訊"), ("神通資訊", "神通資訊"),
                  ("藍新資訊", "藍新資訊"), ("凱基證券", "凱基證券"), ("華電聯網", "華電聯網"), ("奧衍", "奧衍"),
                  ("中華網龍", "中華網龍"), ("尼諾思", "尼諾思科技"), ("醫宇宙", "醫宇宙")]
# 常用問題：鍵 -> (按鈕文字, 接在公司名後的句尾)。句型同評估題（「X是做什麼的」「X有哪些…」「X的營收…」）
FAQ = {"what": ("這家做什麼", "是做什麼的？"), "jobs": ("有哪些職缺", "有哪些職缺？"),
       "tech": ("用什麼技術", "用什麼技術？"), "fin": ("財務與新聞", "的營收和近期新聞是什麼？")}
DEMOS = ["u07", "u06"]  # 查無示範：不可回答題的題號
EVAL = {q["id"]: q for q in json.loads((Path(__file__).parent / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]}
LOW = "<p class='warn'><b>可能沒有答案。</b>語料中找不到很接近的內容，也可能只是問法太籠統。下面的原文仍可參考，請自己核對。</p>"


def _hits_html(hits, dim):
    return "".join(
        f"<div class='hit{' dim' if dim else ''}'><b>{escape(h['company'])}</b> · {escape(h['file'])} · "
        f"{escape(h['heading_path'])}<pre>{escape(h['text'])}</pre></div>" for h in hits)


def _eval_panel(q):
    """問句與某題評估題完全相同時，顯示該題在評估裡的名次（跨公司、不套門檻，與評分器一致）。"""
    e = next((e for e in EVAL.values() if e["question"] == q), None)
    if not e:
        return "", ""
    if e["answerable"]:
        r = hit_rank(search(q, k=DEPTH, gate=False), e["gold"])
        txt = f"金標段落排第 {r}（{'命中前 3' if r <= 3 else '未進前 3'}）" if r else f"前 {DEPTH} 名內沒有金標段落（未命中）"
    else:
        txt = "不可回答題：語料中沒有答案，正確結果是「可能沒有答案」。"
    return " <a href='#eval'>看這題在評估裡的成績</a>", f"<div id=eval class='ans'><b>評估成績（{escape(e['id'])}）</b><p>{escape(txt)}</p></div>"


@app.get("/")
def index():
    a = request.args
    company = (a["pick"] if "pick" in a else a.get("company", "")).strip() or None
    q, note = a.get("q", "").strip(), ""
    if a.get("demo") in DEMOS:
        q, company = EVAL[a["demo"]]["question"], None
    elif a.get("faq") in FAQ:
        label = next((l for l, n in LIVE_COMPANIES if n == company), company)
        if company:
            q = f"{label}{FAQ[a['faq']][1]}"
        else:
            q, note = "", "<p class='warn'>請先選一家公司，再按常用問題；或直接在上面輸入問題（跨公司）。</p>"
    body, err, ans, link, panel = "", "", "", "", ""
    if q:
        link, panel = _eval_panel(q)
        try:
            hits = search(q, company=company, gate=False)  # 預設檢索方式沿用 job_rag；載入模型很慢，只搜一次
            # 最高分低於 job_rag 的門檻：仍顯示原文（淡色），不整理成答案。
            low = not hits or hits[0]["score"] < retrieval.NOT_FOUND_THRESHOLD
            body = (LOW if low else "") + _hits_html(hits, low)
            if hits and not low:
                if a.get("answer"):
                    try:
                        r = answer(q, hits, post=_post)
                        src = "".join(f"<li>{escape(s['company'])} · {escape(s['file'])} · {escape(s['heading_path'])}</li>" for s in r["sources"])
                        ans = f"<div class='ans'><b>答案</b><pre>{escape(r['answer'])}</pre><ul>{src}</ul></div>"
                    except AnswerError as e:
                        ans = f"<p class='err'>整理失敗：{escape(e)}（原文結果不受影響）</p>"
                else:
                    ans = "<button name=answer value=1 form=f>整理成答案</button>"
        except RuntimeError as e:
            err = f"<p class='err'>錯誤：{escape(e)}</p>"
    pick = "".join(
        f"<button name=pick value=\"{'' if name == company else name}\"{' class=sel' if name == company else ''}>{label}</button>"
        for label, name in LIVE_COMPANIES)
    faq = "".join(f"<button name=faq value={k}>{label}</button>" for k, (label, _) in FAQ.items())
    demo = "".join(f"<button name=demo value=\"{i}\" class=demo>{escape(EVAL[i]['question'])}</button>" for i in DEMOS)
    return f"""<!doctype html><html lang=zh-Hant><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>求職情報問答</title>
<style>*{{box-sizing:border-box}}body{{font-family:sans-serif;max-width:800px;margin:auto;padding:0 12px;overflow-wrap:anywhere}}
.row{{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}}button{{min-height:44px;padding:6px 14px;font-size:16px}}
.sel{{background:#1a5fb4;color:#fff}}.demo{{text-align:left}}input{{width:100%;min-height:44px;font-size:16px}}
.hit{{border:1px solid #ccc;padding:8px;margin:8px 0}}.dim{{opacity:.45}}.ans{{background:#f3f8ff;padding:8px;margin:8px 0}}
.warn{{background:#fff4d6;padding:8px}}.err{{color:#c00}}pre{{white-space:pre-wrap}}h4{{margin:12px 0 0}}</style>
<h1>求職情報問答</h1>
<form id=f><input type=hidden name=company value="{escape(company or '')}">
<h4>1. 選一家公司（再按一次取消，不選就查全部）</h4><div class=row>{pick}</div>
<h4>2. 常用問題</h4><div class=row>{faq}</div>
<h4>或自己輸入問題</h4><input name=q value="{escape(q)}" placeholder="輸入問題"><div class=row><button>查</button></div>
<h4>查無示範（語料裡沒有答案的問題）</h4><div class=row>{demo}</div></form>
{note}{err}{body}{ans}{link}{panel}"""


if __name__ == "__main__":
    app.run(port=5000)

"""求職情報問答（Flask 單頁）。python -X utf8 app.py"""
import json
import os
import threading
from pathlib import Path

from flask import Flask, request
from markupsafe import escape

from job_rag import about, detect_company, netinfo, public_company_counts, retrieval, search
from job_rag.about_page import render as render_about
from job_rag.answer import AnswerError, _post, answer
from job_rag.evaluate import DEPTH, hit_rank
from job_rag.ui import page

app = Flask(__name__)

# 預熱：啟動時先載入 bge-m3 與索引。state：loading（準備中）、ready、error。測試與直接 import 時預設 ready。
_warm = {"state": "ready", "error": ""}


def _on(name):  # 兩個開關預設開；環境變數設 0 關掉（比較成績用）
    return os.environ.get(name, "1") != "0"


def warmup():
    try:
        search("預熱", gate=False)  # 載入模型、建索引、編碼一次查詢
        _warm["state"] = "ready"
    except Exception as e:  # 失敗要讓使用者看到，不假裝可用
        _warm.update(state="error", error=str(e))


def start_warmup():
    _warm["state"] = "loading"
    threading.Thread(target=warmup, daemon=True).start()


_phone = {"cands": None}  # 啟動時偵測的區網位址；None 表示沒偵測過（測試與直接 import）


def _phone_footer():
    """只在手機模式、且請求來自本機時，頁尾顯示一行小字，讓人在筆電畫面上看到手機要輸入的網址。"""
    if not netinfo.phone_mode() or request.remote_addr not in ("127.0.0.1", "::1"):
        return ""
    cands = _phone["cands"] if _phone["cands"] is not None else netinfo.detect()
    port = os.environ.get("JOB_RAG_PORT", "5000")
    return f"<small>{str(escape(netinfo.banner(cands, port))).replace(chr(10), '<br>')}</small>"


def _status_page():
    if _warm["state"] == "error":
        body = f"<main class=status><h1>求職情報問答</h1><p class=err>啟動失敗：{escape(_warm['error'])}</p></main>"
        return page("求職情報問答", body)
    body = ("<main class=status role=status><div class=dot></div><h1>求職情報問答</h1>"
            "<p><b>準備中</b>：正在載入模型與索引，完成後會自動顯示查詢頁。</p></main>")
    return page("求職情報問答", body, "<meta http-equiv=refresh content=2>")


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
        f"{escape(h['heading_path'])}<pre>{escape(h['text'])}</pre>{_also(h)}</div>" for h in hits)


def _also(h):
    if not h.get("also_in"):
        return ""
    return "<small>也出現於：" + "；".join(f"{escape(a['file'])} · {escape(a['heading_path'])}" for a in h["also_in"]) + "</small>"


def _eval_panel(q):
    """問句與某題評估題完全相同時，顯示該題在評估裡的名次（不套門檻；公司過濾與去重開關同下面的查詢）。"""
    e = next((e for e in EVAL.values() if e["question"] == q), None)
    if not e:
        return "", ""
    if e["answerable"]:
        r = hit_rank(search(q, k=DEPTH, gate=False, detect=_on("JOB_RAG_DETECT"), dedupe=_on("JOB_RAG_DEDUPE")), e["gold"])
        txt = f"金標段落排第 {r}（{'命中前 3' if r <= 3 else '未進前 3'}）" if r else f"前 {DEPTH} 名內沒有金標段落（未命中）"
    else:
        txt = "不可回答題：語料中沒有答案，正確結果是「可能沒有答案」。"
    return "<p class=link><a href='#eval'>看這題在評估裡的成績</a></p>", f"<div id=eval class='ans'><b>評估成績（{escape(e['id'])}）</b><p>{escape(txt)}</p></div>"


@app.get("/about")
def about_page():
    if _warm["state"] != "ready":  # 預熱期間與問答頁一致
        return _status_page()
    counts = public_company_counts()
    n_company = len([c for c in counts if c != "綜合"])  # 「綜合」是無法歸屬的段落，不算公司
    try:
        return render_about(about.load(), "", sum(counts.values()), n_company)
    except about.AboutDataError as e:  # 輸出檔缺、壞、過期：顯示錯誤，不用舊數字
        return render_about(None, str(e), sum(counts.values()), n_company), 500


@app.get("/")
def index():
    if _warm["state"] != "ready":
        return _status_page()
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
            use = company  # 介面選的公司優先；沒選才用問句偵測到的
            if not use and _on("JOB_RAG_DETECT") and (use := detect_company(q)):
                note += f"<p class='warn'>已偵測到公司：{escape(use)}，只搜這一家。要查全部公司，請把問句裡的公司名拿掉。</p>"
            hits = search(q, company=use, gate=False, dedupe=_on("JOB_RAG_DEDUPE"))  # 預設檢索方式沿用 job_rag；載入模型很慢，只搜一次
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
                    ans = "<button class=go name=answer value=1 form=f>整理成答案</button>"
        except RuntimeError as e:
            err = f"<p class='err'>錯誤：{escape(e)}</p>"
    pick = "".join(
        f"<button name=pick value=\"{'' if name == company else name}\" aria-pressed={'true class=sel' if name == company else 'false'}>{label}</button>"
        for label, name in LIVE_COMPANIES)
    faq = "".join(f"<button name=faq value={k}>{label}</button>" for k, (label, _) in FAQ.items())
    demo = "".join(f"<button name=demo value=\"{i}\" class=demo>{escape(EVAL[i]['question'])}</button>" for i in DEMOS)
    return page("求職情報問答", f"""<nav><b>問答</b><a href="/about">專案說明</a></nav>
<h1>求職情報問答</h1>
<form id=f><input type=hidden name=company value="{escape(company or '')}">
<h3>1. 選一家公司（再按一次取消，不選就查全部）</h3><div class=grid>{pick}</div>
<h3>2. 常用問題</h3><div class="grid faq">{faq}</div>
<h3>或自己輸入問題</h3><div class=ask><input name=q value="{escape(q)}" placeholder="輸入問題" enterkeyhint=search><button class=go>查</button></div>
<h3>查無示範（語料裡沒有答案的問題）</h3><div class=row>{demo}</div></form>
{note}{err}{body}{ans}{link}{panel}{_phone_footer()}""")


if __name__ == "__main__":
    start_warmup()
    port = int(os.environ.get("JOB_RAG_PORT", "5000"))
    if netinfo.phone_mode():  # 手機模式：對區網開放（僅區網；不做通道或轉發）。印出手機要開的網址
        _phone["cands"] = netinfo.detect()
        print(netinfo.banner(_phone["cands"], port), flush=True)
    app.run(host=netinfo.listen_host(), port=port)

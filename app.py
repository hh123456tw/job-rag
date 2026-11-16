"""求職情報問答（Flask 單頁）。python -X utf8 app.py"""
import json
import os
import threading
import time
import urllib.error
from urllib.parse import quote, urlencode
from pathlib import Path

from flask import Flask, g, request
from markupsafe import escape

from job_rag import about, guard, detect_company, netinfo, public_company_counts, retrieval, search
from job_rag.about_page import render as render_about
from job_rag.chat_ui import CHAT_JS
from job_rag.memory import HistoryError, clean_history, expand
from job_rag.topics import topics
from job_rag.answer import NOT_FOUND, AnswerError, _post, answer
from job_rag.evalset import questions_path
from job_rag.evaluate import DEPTH, hit_rank
from job_rag.ui import page

app = Flask(__name__)
_limiter = guard.RateLimit()  # 「整理成答案」的全域用量；測試可換成注入時鐘的版本

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


# (按鈕文字, 語料的公司欄位)。現場 8 家；奧衍、尼諾思、醫宇宙已移出（retrieval.EXCLUDED_COMPANIES）。按鈕文字與公司欄位目前相同。
LIVE_COMPANIES = [("台灣大哥大", "台灣大哥大"), ("聯合報", "聯合報"), ("叡揚資訊", "叡揚資訊"), ("神通資訊", "神通資訊"),
                  ("藍新資訊", "藍新資訊"), ("凱基證券", "凱基證券"), ("華電聯網", "華電聯網"), ("中華網龍", "中華網龍")]
# 常用問題：鍵 -> (按鈕文字, 接在公司名後的句尾)。句型必須通順、對任何公司都適用；措辭挑選見 eval/button_check.md
FAQ = {"what": ("這家做什麼", "是做什麼的？"), "jobs": ("有哪些職缺", "有哪些職缺？"),
       "tech": ("用什麼技術", "的技術堆疊與開發工具有哪些？"), "fin": ("財務與新聞", "的營收和近期新聞是什麼？")}
EVAL = {q["id"]: q for q in json.loads(questions_path().read_text(encoding="utf-8"))["questions"]}
# 查無示範：不可回答題的題號。完整題組用 u07、u06；範例題組沒有這兩題，就用前兩個不可回答題
DEMOS = [i for i in ("u07", "u06") if i in EVAL] or [i for i, q in EVAL.items() if not q["answerable"]][:2]


def _company_buttons():
    """語料只含預設現場公司的一部分時，按鈕改列語料裡有的公司；全有或一家都沒有時用原清單。
    例外：公開範例語料（3 家都不是現場公司）直接列它的公司。"""
    names = {n for n in public_company_counts() if n != "綜合"}
    live = {n for _, n in LIVE_COMPANIES}
    if not names & live:
        return [(n, n) for n in sorted(names)] if retrieval.is_sample() else LIVE_COMPANIES
    if live <= names:
        return LIVE_COMPANIES
    label = {n: l for l, n in LIVE_COMPANIES}
    return [(label.get(n, n), n) for n in sorted(names)]
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


@app.before_request
def _require_access_code():
    """JOB_RAG_ACCESS_CODE 有值時，除白名單外都要帶正確的 ?k= 或有效 cookie。沒設時完全不動。"""
    code = guard.access_code()
    if not code or request.path.startswith("/static/") or request.path == "/manifest.webmanifest":
        return None
    if guard.code_ok(request.args.get("k", ""), code):
        g.set_cookie = code  # 第一次帶對了：回應時存成 cookie
    elif not guard.code_ok(request.cookies.get(guard.COOKIE, ""), code):
        if request.path in ("/answer", "/api/answer", "/api/search"):  # 頁面腳本呼叫的端點：回 JSON，不回 HTML
            return {"status": "error", "message": "需要存取碼。請用完整的分享網址重新開啟。"}, 403
        body = "<main class=status><h1>求職情報問答</h1><p>需要存取碼。請用完整的分享網址開啟。</p></main>"
        return page("求職情報問答", body), 403
    return None


@app.after_request
def _remember_access_code(resp):
    if g.get("set_cookie"):
        secure = request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"
        resp.set_cookie(guard.COOKIE, g.set_cookie, httponly=True, samesite="Lax", secure=secure)
    return resp


@app.get("/manifest.webmanifest")
def manifest():  # 路徑都是根路徑相對，http 區網 IP 與 https 通用；預熱期間也可取得
    icons = [{"src": f"/static/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any maskable"} for n in (192, 512)]
    m = {"name": "求職情報問答", "short_name": "求職問答", "start_url": "/", "scope": "/", "display": "standalone",
         "lang": "zh-Hant", "theme_color": "#fafaf9", "background_color": "#fafaf9", "icons": icons}
    return app.response_class(json.dumps(m, ensure_ascii=False), mimetype="application/manifest+json")


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


def _low(hits):
    return not hits or hits[0]["score"] < retrieval.NOT_FOUND_THRESHOLD


def _fake_post():
    """開發用替身（票 21）：只有環境變數 JOB_RAG_FAKE_ANSWER 設成 ok／slow／fail 才啟用；預設沒設，啟動檔也不會設。"""
    mode = os.environ.get("JOB_RAG_FAKE_ANSWER", "")
    if mode not in ("ok", "slow", "fail"):
        return None

    def post(url, headers, body, timeout):
        if mode == "fail":
            raise urllib.error.URLError("開發用替身：模擬無網路")
        if mode == "slow":
            time.sleep(4)
        return {"choices": [{"message": {"content": "（開發用替身的模擬答案）這家公司做的事情寫在原文第 1 段 [1]。"}}]}
    return post


@app.get("/api/answer")
@app.get("/answer")
def answer_json():
    """頁面 JS 取得答案用。與 /?answer=1 同一套規則：低分不呼叫、計入每小時用量、失敗回明確訊息。"""
    q, company = request.args.get("q", "").strip(), request.args.get("company", "").strip() or None
    if not q:
        return {"status": "error", "message": "沒有問題"}, 400
    try:
        history = clean_history(request.args.get("history", ""))  # 伺服器不存對話：每次由前端帶最近 2 輪
    except HistoryError as e:
        return {"status": "error", "message": str(e)}, 400
    if _warm["state"] != "ready":
        return {"status": "error", "message": "系統準備中，請稍後再試（原文結果不受影響）。"}, 503
    try:
        hits = search(expand(q, history), company=company, gate=False, dedupe=_on("JOB_RAG_DEDUPE"))
    except RuntimeError as e:
        return {"status": "error", "message": f"錯誤：{e}"}, 500
    if _low(hits):
        return {"status": "low"}
    if wait := _limiter.try_acquire(guard.answer_limit()):
        return {"status": "limit", "message": f"整理成答案已達每小時 {guard.answer_limit()} 次的上限，"
                f"請約 {-(-wait // 60)} 分鐘後再試。原文在下面，不受影響。"}, 429
    try:
        r = answer(q, hits, post=_fake_post() or _post, history=history)
    except AnswerError as e:
        return {"status": "error", "message": f"整理失敗：{e}。原文在下面，不受影響。"}, 502
    return {"status": "ok", "answer": r["answer"], "sources": r["sources"]}


@app.get("/api/search")
def api_search():
    """對話介面第一步：立刻回段落與是否低分（不呼叫 LLM、不計用量）。"""
    q, company = request.args.get("q", "").strip(), request.args.get("company", "").strip() or None
    if not q:
        return {"status": "error", "message": "沒有問題"}, 400
    try:
        history = clean_history(request.args.get("history", ""))
    except HistoryError as e:
        return {"status": "error", "message": str(e)}, 400
    if _warm["state"] != "ready":
        return {"status": "error", "message": "系統準備中，請稍後再試。"}, 503
    try:
        detected, rq = False, expand(q, history)  # 追問補全後的問句：公司偵測與檢索都用它
        if not company and _on("JOB_RAG_DETECT") and (d := detect_company(rq)):
            company, detected = d, True
        hits = search(rq, company=company, gate=False, dedupe=_on("JOB_RAG_DEDUPE"))
    except RuntimeError as e:
        return {"status": "error", "message": f"搜尋失敗：{e}"}, 500
    keep = ("company", "file", "heading_path", "text", "also_in")
    return {"status": "low" if _low(hits) else "ok", "company": company or "", "detected": detected, "expanded": rq != q.strip(),
            "hits": [{k: h.get(k, []) for k in keep} for h in hits]}


# 答案卡的載入腳本：先把原文收起來（沒有 JS 時維持展開），呼叫 /answer；任何失敗都把原文展開。文字一律用 textContent。
LOAD_JS = """(function(){var d=document.getElementById('raw'),a=document.getElementById('answer'),t=document.getElementById('ans-body'),
c=new AbortController(),to=setTimeout(function(){c.abort()},40000);d.open=false;
function fail(m){clearTimeout(to);t.textContent=m;t.className='err';a.setAttribute('aria-busy','false');d.open=true}
fetch('/answer?'+new URLSearchParams({q:a.dataset.q,company:a.dataset.company}),{signal:c.signal})
.then(function(r){return r.json().catch(function(){return{status:'error',message:'整理失敗：回應格式不符。原文在下面。'}})})
.then(function(j){clearTimeout(to);
if(j.status!=='ok'){fail(j.message||'整理失敗。原文在下面。');return}
a.setAttribute('aria-busy','false');t.className='';t.textContent=j.answer;
if(j.answer==='查無'){t.textContent='查無：語料裡沒有明確的答案。原文在下面，請自己核對。';d.open=true;return}
var u=document.createElement('ul');j.sources.forEach(function(s){var l=document.createElement('li');
l.textContent=s.company+' · '+s.file+' · '+s.heading_path;u.appendChild(l)});a.appendChild(u)})
.catch(function(){fail('整理失敗：逾時或無法連線。原文在下面。')})})();"""


def _top(*links):
    return "<nav class=top>" + "".join(f'<a href="{h}">{t}</a>' for h, t in links) + "</nav>"


def _foot():
    return f'<footer><a href="/about">專案說明</a></footer>{_phone_footer()}'


def _ask(q=""):
    return (f'<div class=ask><input name=q value="{escape(q)}" placeholder="輸入問題" enterkeyhint=search aria-label="輸入問題">'
            "<button class=go>查</button></div>")


PRESETS = json.loads((Path(__file__).parent / "job_rag" / "company_presets.json").read_text(encoding="utf-8"))
ALL = "全部公司"


def _presets(label):
    """該公司的預設題目 [(鍵, 按鈕文字, 完整問句)]。檔案裡沒有的公司（例如範例語料）用最前面 3 個常用問題。"""
    if label == ALL:
        return [(p["key"], p["label"], p["q"]) for p in PRESETS["all"]]
    if label in PRESETS["companies"]:
        return [(p["key"], p["label"], p["q"]) for p in PRESETS["companies"][label]["presets"]]
    return [(k, l, f"{label}{t}") for k, (l, t) in list(FAQ.items())[:3]]


def _home_inner(note=""):
    counts = public_company_counts()
    cards = "".join(f'<a class=card href="/c/{quote(label)}"><b>{escape(label)}</b><span>{counts.get(name, 0)} 段公開資料</span></a>'
                    for label, name in _company_buttons())
    cards += f'<a class="card all" href="/c/{quote(ALL)}"><b>{ALL}</b><span>跨公司提問</span></a>'
    demo = "".join(f'<a class=card href="/?demo={i}"><span>{escape(EVAL[i]["question"])}</span></a>' for i in DEMOS)
    return f"""<main><h1>求職情報問答</h1><p class=sub>點一家公司，直接問問題</p>{note}
<div class=cards>{cards}</div>
<details class=more><summary>查無示範</summary><p class=mute>語料裡沒有答案的問題，結果會顯示「可能沒有答案」。</p><div class=cards>{demo}</div></details></main>{_foot()}"""


def _home(note=""):
    return page("求職情報問答", _home_inner(note))


def _company_inner(company):
    label = next((l for l, n in LIVE_COMPANIES if n == company), company)
    faq = "".join(f"<button name=faq value={k}>{l}</button>" for k, (l, _) in FAQ.items())
    return f"""<main>{_top(("/", "← 公司清單"))}<h1>{escape(label)}</h1><p class=sub>點一個問題</p>
<form id=f><button hidden>查</button><input type=hidden name=company value="{escape(company)}"><div class=faq>{faq}</div>
<h3>或自己輸入問題</h3>{_ask()}</form></main>{_foot()}"""


THIN = 20  # 公開段落少於這個數，才在提示裡明說「公開資料較少」


def _hint(scope, presets, thin):
    """「我能回答什麼」提示的幾行字：主題、筆數、沒有的資料都由載入的語料算出（job_rag/topics.py）。"""
    t = topics(scope or None)
    ex = "你可以這樣問：" + "".join(f"「{q}」" for _, _, q in presets[:2])
    if not scope:
        n = len([c for c in public_company_counts() if c != "綜合"])
        return [f"這裡同時搜 {n} 家公司、共 {t['segments']} 段公開資料。", "沒有的資料：" + "、".join(t["missing"]), ex]
    lines = ["這家有的資料：" + "、".join(t["have"]), "這家沒有的資料：" + "、".join(t["missing"]), ex]
    if thin and t["segments"] < THIN:
        lines.insert(0, f"這家公開資料較少（只有 {t['segments']} 段），答案可能很短。")
    return lines


@app.get("/c/<label>")
def chat(label):
    """每一家公司（與「全部公司」）各一個對話頁。沒有 JS 時顯示 noscript 裡的伺服器渲染版本。"""
    if _warm["state"] != "ready":
        return _status_page()
    names = dict(_company_buttons())
    if label != ALL and label not in names:
        return page("找不到", "<main class=status><h1>找不到這家公司</h1><p><a href=\"/\">← 公司清單</a></p></main>"), 404
    scope = "" if label == ALL else names[label]
    hello = (f"我可以回答關於{label}的問題。你可以點下面的題目，或直接問。" if scope
             else "我可以跨公司回答問題。你可以點下面的題目，或直接問。")
    presets = _presets(label)
    hint = _hint(scope, presets, PRESETS["companies"].get(label, {}).get("thin"))
    attrs = {"presets": json.dumps(presets, ensure_ascii=False), "hint": json.dumps(hint, ensure_ascii=False), "scope": scope,
             "label": label, "key": label, "hello": hello}
    data = " ".join(f'data-{k}="{escape(v)}"' for k, v in attrs.items())
    fallback = _company_inner(scope) if scope else _home_inner()
    return page(f"{label}｜求職情報問答", f"""<body class=chat {data}>
<header><a href="/">← 公司清單</a><b class=app>{escape(label)}</b><button id=help type=button aria-label="可以問什麼">？</button><a href="/about">專案說明</a></header>{_phone_footer()}
<div id=thread role=log aria-live=polite></div>
<form id=bar autocomplete=off><input id=qi name=q placeholder="{escape('例如：' + presets[0][2])}" enterkeyhint=send aria-label="輸入問題"><button class=go>送出</button></form>
<noscript><style>#thread,#bar{{display:none}}</style>{fallback}</noscript><script>{CHAT_JS}</script>""")


@app.get("/")
def index():
    if _warm["state"] != "ready":
        return _status_page()
    a = request.args
    company = a.get("company", "").strip() or None
    q, note = a.get("q", "").strip(), ""
    if a.get("demo") in DEMOS:
        q, company = EVAL[a["demo"]]["question"], None
    elif a.get("faq") in FAQ:
        label = next((l for l, n in LIVE_COMPANIES if n == company), company)
        if company:
            q = f"{label}{FAQ[a['faq']][1]}"
        else:
            note = "<p class='warn'>請先選一家公司，再點問題；或直接輸入問題（查全部公司）。</p>"
    if not q:
        return page("求職情報問答", _company_inner(company) if company and not note else _home_inner(note))
    link, panel = _eval_panel(q)
    err, ans, status, card, raw, use, raw_open = "", "", 200, "", "", company, True
    try:
        if not use and _on("JOB_RAG_DETECT") and (use := detect_company(q)):
            note += f"<p class='warn'>已偵測到公司：{escape(use)}，只搜這一家。要查全部公司，請把問句裡的公司名拿掉。</p>"
        hits = search(q, company=use, gate=False, dedupe=_on("JOB_RAG_DEDUPE"))  # 預設檢索方式沿用 job_rag；載入模型很慢，只搜一次
        low = _low(hits)  # 最高分低於門檻：不呼叫 DeepSeek，原文淡色並展開
        raw = (LOW if low else "") + _hits_html(hits, low)
        if hits and not low:
            if a.get("answer"):  # 沒有 JS 時的退路：伺服器端整理（與 /answer 同樣計次）
                if wait := _limiter.try_acquire(guard.answer_limit()):
                    status = 429
                    ans = (f"<p class='err'>整理成答案已達每小時 {guard.answer_limit()} 次的上限，"
                           f"請約 {-(-wait // 60)} 分鐘後再試（原文結果不受影響）。</p>")
                else:
                    try:
                        r = answer(q, hits, post=_fake_post() or _post)
                        src = "".join(f"<li>{escape(s['company'])} · {escape(s['file'])} · {escape(s['heading_path'])}</li>" for s in r["sources"])
                        ans = f"<div class='ans'><b>答案</b><pre>{escape(r['answer'])}</pre><ul>{src}</ul></div>"
                        raw_open = r["answer"] == NOT_FOUND
                    except AnswerError as e:
                        ans = f"<p class='err'>整理失敗：{escape(e)}（原文結果不受影響）</p>"
            else:
                href = "/?" + urlencode({"q": q, "company": company or "", "answer": 1})
                card = (f'<section id=answer class=ans aria-live=polite aria-busy=true data-q="{escape(q)}" data-company="{escape(use or "")}">'
                        f"<b>答案</b><p id=ans-body>整理中…</p><noscript><style>#ans-body{{display:none}}</style>"
                        f'<a class=btn href="{escape(href)}">整理成答案</a></noscript></section>')
    except RuntimeError as e:
        err = f"<p class='err'>錯誤：{escape(e)}</p>"
    details = f"<details id=raw{' open' if raw_open else ''}><summary>看原文</summary>{raw}</details>" if raw else ""
    script = f"<script>{LOAD_JS}</script>" if card else ""
    clabel = next((l for l, n in _company_buttons() if n == company), company)
    back = [(f"/c/{quote(clabel)}", "← 換問題"), ("/", "← 公司清單")] if company else [("/", "← 換問題")]
    return page("求職情報問答", f"""<main>{_top(*back)}<p class=q>{escape(q)}</p>
<div id=results>{note}{err}{card}{ans}{details}{script}{link}{panel}</div></main>{_foot()}"""), status


if __name__ == "__main__":
    start_warmup()
    port = int(os.environ.get("JOB_RAG_PORT", "5000"))
    if netinfo.phone_mode():  # 手機模式：對區網開放（僅區網；不做通道或轉發）。印出手機要開的網址
        _phone["cands"] = netinfo.detect()
        print(netinfo.banner(_phone["cands"], port), flush=True)
    app.run(host=netinfo.listen_host(), port=port)

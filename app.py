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

from job_rag import about, cross_search, guard, is_cross, detect_company, netinfo, owner_ui, public_company_counts, retrieval, search
from job_rag.selfdata import IV_ALL, IV_COMPANY
from job_rag.owner import COOKIE as OWNER_COOKIE, TTL as OWNER_TTL, Owner
from job_rag.about_page import render as render_about
from job_rag.about_slides import render as render_slides
from job_rag import threshold_page
from job_rag.chat_ui import CHAT_JS
from job_rag.memory import HistoryError, clean_history, expand
from job_rag.topics import topics
from job_rag.answer import NOT_FOUND, AnswerError, _post, answer
from job_rag.evalset import questions_path
from job_rag.evaluate import DEPTH, hit_rank
from job_rag.ui import page

app = Flask(__name__)
_limiter = guard.RateLimit()  # 「整理成答案」的全域用量；測試可換成注入時鐘的版本
_owner = Owner()  # 本人密碼與簽名 cookie（票 24）；金鑰每次啟動隨機產生，重啟即失效


def _mode() -> str:
    """這個請求的模式。只看有效的本人 cookie；查詢參數、history、表單值一律不參與決定。沒有或無效＝展示。"""
    if "mode" not in g:
        g.mode = "self" if _owner.valid(request.cookies.get(OWNER_COOKIE)) else "demo"
    return g.mode


def _tag(d: dict) -> dict:
    """設了本人密碼時，API 回應帶目前模式，前端據此發現模式變了（cookie 過期、別的分頁登出）而清掉自用畫面。"""
    return d | {"mode": _mode()} if _owner.enabled else d


def _secure() -> bool:
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"

# 預熱：啟動時先載入 bge-m3 與索引。state：loading（準備中）、ready、error。測試與直接 import 時預設 ready。
_warm = {"state": "ready", "error": "", "self": "ready", "self_error": ""}


def _on(name):  # 兩個開關預設開；環境變數設 0 關掉（比較成績用）
    return os.environ.get(name, "1") != "0"


def warmup():
    try:
        search("預熱", gate=False)  # 載入模型、建索引、編碼一次查詢
        _warm["state"] = "ready"
    except Exception as e:  # 失敗要讓使用者看到，不假裝可用
        _warm.update(state="error", error=str(e))
        return
    if _owner.enabled:  # 自用索引（私人段落＋面經）也預先編碼；只在本機記憶體與 .cache/
        try:
            search("預熱", gate=False, mode="self")
            _warm["self"] = "ready"
        except Exception as e:
            _warm.update({"self": "error", "self_error": str(e)})


def start_warmup():
    _warm["state"] = "loading"
    _warm["self"] = "loading" if _owner.enabled else "ready"
    threading.Thread(target=warmup, daemon=True).start()


_phone = {"cands": None}  # 啟動時偵測的區網位址；None 表示沒偵測過（測試與直接 import）


def _phone_footer():
    """只在手機模式、且請求來自本機時，頁尾顯示一行小字，讓人在筆電畫面上看到手機要輸入的網址。"""
    if not netinfo.phone_mode() or request.remote_addr not in ("127.0.0.1", "::1"):
        return ""
    cands = _phone["cands"] if _phone["cands"] is not None else netinfo.detect()
    port = os.environ.get("JOB_RAG_PORT", "5000")
    return f"<small>{str(escape(netinfo.banner(cands, port))).replace(chr(10), '<br>')}</small>"


def _self_wait(mode: str) -> str:
    """自用模式且自用索引還沒好時的說明；好了或不是自用模式回空字串。"""
    if mode != "self" or _warm["self"] == "ready":
        return ""
    if _warm["self"] == "error":
        return f"自用索引載入失敗：{_warm['self_error']}"
    return "自用索引準備中（第一次要編碼筆記與面經，需幾分鐘）。"


def _status_page(mode="demo"):
    if mode == "self" and _warm["state"] == "ready" and (msg := _self_wait(mode)):
        refresh = "" if _warm["self"] == "error" else "<meta http-equiv=refresh content=5>"
        return page("求職情報問答", owner_ui.chrome(mode, True) + f"<main class=status role=status><h1>求職情報問答</h1><p>{escape(msg)}</p></main>", refresh)
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


def _company_buttons(mode="demo"):
    """語料只含預設現場公司的一部分時，按鈕改列語料裡有的公司；全有或一家都沒有時用原清單。
    例外：公開範例語料（3 家都不是現場公司）直接列它的公司。"""
    names = {n for n in public_company_counts(mode=mode) if n != "綜合"}
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
        f"<div class='hit{' dim' if dim else ''}'>{'<span class=priv>自用資料</span>' if h.get('private') else ''}"
        f"<b>{escape(h['company'])}</b> · {escape(h['file'])} · "
        f"{escape(h['heading_path'])}<pre>{escape(h['text'])}</pre>{_also(h)}</div>" for h in hits)


def _also(h):
    if not h.get("also_in"):
        return ""
    return "<small>也出現於：" + "；".join(f"{escape(a['file'])} · {escape(a['heading_path'])}" for a in h["also_in"]) + "</small>"


def _eval_panel(q):
    """問句與某題評估題完全相同時，顯示該題在評估裡的名次（不套門檻；公司過濾與去重開關同下面的查詢）。評估只量展示索引。"""
    if _mode() == "self":
        return "", ""
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
    if os.environ.get("JOB_RAG_LOCAL_OPEN") == "1" and request.remote_addr in ("127.0.0.1", "::1") and "X-Forwarded-For" not in request.headers:  # 公開模式下，本機直連免存取碼；經代理轉進來的請求一定帶 X-Forwarded-For
        return None
    if guard.code_ok(request.args.get("k", ""), code):
        g.set_cookie = code  # 第一次帶對了：回應時存成 cookie
    elif not guard.code_ok(request.cookies.get(guard.COOKIE, ""), code):
        if request.path in ("/answer", "/api/answer", "/api/search", "/api/owner/login", "/api/owner/logout"):  # 頁面腳本呼叫的端點：回 JSON，不回 HTML
            return {"status": "error", "message": "需要存取碼。請用完整的分享網址重新開啟。"}, 403
        body = "<main class=status><h1>求職情報問答</h1><p>需要存取碼。請用完整的分享網址開啟。</p></main>"
        return page("求職情報問答", body), 403
    return None


@app.after_request
def _remember_access_code(resp):
    if g.get("set_cookie"):
        resp.set_cookie(guard.COOKIE, g.set_cookie, httponly=True, samesite="Lax", secure=_secure())
    if _owner.enabled and not request.path.startswith("/static/"):
        resp.headers["Vary"] = "Cookie"  # 同一網址依 cookie 有兩種內容
        if _mode() == "self":
            resp.headers["Cache-Control"] = "no-store"  # 登出後按上一頁不該看到自用畫面
    return resp


@app.post("/api/owner/login")
def owner_login():
    """切到自用：密碼在 JSON body（不放網址）。沒設本人密碼＝沒有這個功能（404）。錯誤次數全域計算，超過回 429。"""
    if not _owner.enabled:
        return {"status": "error", "message": "沒有自用模式"}, 404
    j = request.get_json(silent=True)
    if not isinstance(j, dict):
        return {"status": "error", "message": "請求格式不符"}, 400
    result, cookie = _owner.login(j.get("pin"))
    if result == "locked":
        return {"status": "error", "message": "錯誤次數過多，請稍後再試。"}, 429
    if result != "ok":
        return {"status": "error", "message": "密碼錯誤"}, 401
    resp = app.response_class(json.dumps({"status": "ok", "mode": "self"}), mimetype="application/json")
    resp.set_cookie(OWNER_COOKIE, cookie, max_age=OWNER_TTL, httponly=True, samesite="Lax", secure=_secure())
    return resp


@app.post("/api/owner/logout")
def owner_logout():
    """切回展示：清掉本人 cookie，立即生效。"""
    if not _owner.enabled:
        return {"status": "error", "message": "沒有自用模式"}, 404
    resp = app.response_class(json.dumps({"status": "ok", "mode": "demo"}), mimetype="application/json")
    resp.delete_cookie(OWNER_COOKIE, httponly=True, samesite="Lax", secure=_secure())
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
    names = [c for c in counts if c != "綜合"]  # 「綜合」是無法歸屬的段落，不算公司
    # 預設是簡報；?all=1 是原本的長頁（含全部文字說明）
    render = render_about if request.args.get("all") == "1" else lambda *a: render_slides(*a, companies=names)
    args = (sum(counts.values()), len(names), retrieval.public_segment_lengths())
    try:
        return render(about.load(), "", *args)
    except about.AboutDataError as e:  # 輸出檔缺、壞、過期：顯示錯誤，不用舊數字
        return render(None, str(e), *args), 500


@app.get("/threshold")
def threshold():  # 只讀輸出檔與常數，不用模型，預熱期間也能開；缺檔由頁面註明，不報 500
    return threshold_page.render(threshold_page.load())


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _is_cross(rq, company, mode) -> bool:
    """跨公司題：沒指定公司、問句沒提到公司、含跨公司詞（job_rag.retrieval.is_cross）。"""
    return not company and is_cross(rq, mode=mode)


def _cross_hits(rq, mode):
    """跨公司檢索：只取介面列出的公司（現場 8 家；索引裡其他公司沒有按鈕，不列入）。對不上任何一家時退回索引裡全部公司。"""
    names = set(public_company_counts(mode=mode)) - {"綜合"}
    return cross_search(rq, mode=mode, companies=({n for _, n in _company_buttons(mode)} & names) or None)


def _low_cross(hits):
    return not hits or max(h["score"] for h in hits) < retrieval.CROSS_FLOOR


def _thr(company):
    return round(retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP, 3) if company else retrieval.NOT_FOUND_THRESHOLD


def _low(hits, company=None):
    return not hits or hits[0]["score"] < _thr(company)


def _fake_post():
    """開發用替身（票 21）：只有環境變數 JOB_RAG_FAKE_ANSWER 設成 ok／slow／fail／usage 才啟用；預設沒設，啟動檔也不會設。"""
    mode = os.environ.get("JOB_RAG_FAKE_ANSWER", "")
    if mode not in ("ok", "slow", "fail", "usage"):
        return None

    def post(url, headers, body, timeout):
        if mode == "fail":
            raise urllib.error.URLError("開發用替身：模擬無網路")
        if mode == "slow":
            time.sleep(4)
        r = {"choices": [{"message": {"content": "（開發用替身的模擬答案）這家公司做的事情寫在原文第 1 段 [1]。"}}]}
        # 替身：usage 模式回假的 token 數，只供畫面測試；真的 DeepSeek 才有真用量
        return r | ({"usage": {"prompt_tokens": 1234, "completion_tokens": 56}} if mode == "usage" else {})
    return post


@app.get("/api/answer")
@app.get("/answer")
def answer_json():
    """頁面 JS 取得答案用。與 /?answer=1 同一套規則：低分不呼叫、計入每小時用量、失敗回明確訊息。"""
    q, company = request.args.get("q", "").strip(), request.args.get("company", "").strip() or None
    if not q:
        return {"status": "error", "message": "沒有問題"}, 400
    mode = _mode()
    try:
        history = clean_history(request.args.get("history", ""), mode)  # 伺服器不存對話；只收標記為本模式的輪次
    except HistoryError as e:
        return _tag({"status": "error", "message": str(e)}), 400
    if _warm["state"] != "ready":
        return _tag({"status": "error", "message": "系統準備中，請稍後再試（原文結果不受影響）。"}), 503
    if msg := _self_wait(mode):
        return _tag({"status": "error", "message": msg}), 503
    try:
        rq = q if _is_cross(q, company, mode) else expand(q, history, mode=mode)  # 本身就是跨公司題就不接上一題（否則上一題的公司名會把它變成單公司）
        cross = _is_cross(rq, company, mode)
        hits = _cross_hits(rq, mode) if cross else search(rq, company=company, gate=False, dedupe=_on("JOB_RAG_DEDUPE"), mode=mode)
    except RuntimeError as e:
        return _tag({"status": "error", "message": f"錯誤：{e}"}), 500
    if _low_cross(hits) if cross else _low(hits, company):
        return _tag({"status": "low"})
    if wait := _limiter.try_acquire(guard.answer_limit()):
        return _tag({"status": "limit", "message": f"整理成答案已達每小時 {guard.answer_limit()} 次的上限，"
                     f"請約 {-(-wait // 60)} 分鐘後再試。原文在下面，不受影響。"}), 429
    t0 = time.perf_counter()
    try:
        r = answer(q, hits, post=_fake_post() or _post, history=history, cross=cross)
    except AnswerError as e:
        return _tag({"status": "error", "message": f"整理失敗：{e}。原文在下面，不受影響。"}), 502
    return _tag({"status": "ok", "answer": r["answer"], "sources": r["sources"], "answer_ms": _ms(t0)}
                | ({"usage": r["usage"]} if "usage" in r else {}))


@app.get("/api/search")
def api_search():
    """對話介面第一步：立刻回段落與是否低分（不呼叫 LLM、不計用量）。"""
    q, company = request.args.get("q", "").strip(), request.args.get("company", "").strip() or None
    if not q:
        return {"status": "error", "message": "沒有問題"}, 400
    mode = _mode()
    try:
        history = clean_history(request.args.get("history", ""), mode)
    except HistoryError as e:
        return _tag({"status": "error", "message": str(e)}), 400
    if _warm["state"] != "ready":
        return _tag({"status": "error", "message": "系統準備中，請稍後再試。"}), 503
    if msg := _self_wait(mode):
        return _tag({"status": "error", "message": msg}), 503
    t0 = time.perf_counter()  # 伺服器端檢索耗時（含追問補全、公司偵測、向量檢索）
    try:
        detected, rq = False, (q if _is_cross(q, company, mode) else expand(q, history, mode=mode))  # 追問補全後的問句：公司偵測與檢索都用它；跨公司題不補
        if not company and _on("JOB_RAG_DETECT") and (d := detect_company(rq, mode=mode)):
            company, detected = d, True
        cross = _is_cross(rq, company, mode)
        hits = _cross_hits(rq, mode) if cross else search(rq, company=company, gate=False, dedupe=_on("JOB_RAG_DEDUPE"), mode=mode)
    except RuntimeError as e:
        return _tag({"status": "error", "message": f"搜尋失敗：{e}"}), 500
    search_ms = _ms(t0)
    keep = ("company", "file", "heading_path", "text", "also_in")
    scored = retrieval.DEFAULT_METHOD == "bge-m3"  # 只有 bge-m3 的相似度有「分數／門檻」可比；其他方式不帶，不編
    low = _low_cross(hits) if cross else _low(hits, company)
    return _tag({"status": "low" if low else "ok", "company": company or "", "detected": detected, "expanded": rq != q.strip(), "cross": cross, "per": retrieval.PER_COMPANY if cross else 0,
                 "threshold": retrieval.CROSS_FLOOR if cross else _thr(company), "search_ms": search_ms,
                 "hits": [{k: h.get(k, []) for k in keep} | ({"private": h["private"]} if "private" in h else {})
                          | ({"score": h["score"]} if scored and "score" in h else {}) for h in hits]})


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


def _presets(label, mode="demo", scope=""):
    """該公司的預設題目 [(鍵, 按鈕文字, 完整問句)]。檔案裡沒有的公司（例如範例語料）用最前面 3 個常用問題。
    自用模式且該範圍有面經時，多一組面經相關題：由載入的面經篇數動態決定，題目不存檔。"""
    if label == ALL:
        out = [(p["key"], p["label"], p["q"]) for p in PRESETS["all"]]
    elif label in PRESETS["companies"]:
        out = [(p["key"], p["label"], p["q"]) for p in PRESETS["companies"][label]["presets"]]
    else:
        out = [(k, l, f"{label}{t}") for k, (l, t) in list(FAQ.items())[:3]]
    if mode == "self" and topics(scope or None, mode="self")["interviews"]:
        out += IV_ALL if label == ALL else [(k, l, f"{label}{t}") for k, l, t in IV_COMPANY]
    return out


def _home_inner(note="", mode="demo"):
    counts = public_company_counts(mode=mode)
    unit = "段（含自用資料）" if mode == "self" else "段公開資料"
    cards = "".join(f'<a class=card href="/c/{quote(label)}"><b>{escape(label)}</b><span>{counts.get(name, 0)} {unit}</span></a>'
                    for label, name in _company_buttons(mode))
    cards += f'<a class="card all" href="/c/{quote(ALL)}"><b>{ALL}</b><span>跨公司提問</span></a>'
    demo = "".join(f'<a class=card href="/?demo={i}"><span>{escape(EVAL[i]["question"])}</span></a>' for i in DEMOS)
    return f"""<main><h1>求職情報問答</h1><p class=sub>點一家公司，直接問問題</p>{note}
<div class=cards>{cards}</div>
<details class=more><summary>查無示範</summary><p class=mute>語料裡沒有答案的問題，結果會顯示「可能沒有答案」。</p><div class=cards>{demo}</div></details></main>{_foot()}"""


def _chrome(mode):
    return owner_ui.chrome(mode, _owner.enabled)


def _home(note="", mode="demo"):
    return page("求職情報問答", _chrome(mode) + _home_inner(note, mode))


def _company_inner(company):
    label = next((l for l, n in LIVE_COMPANIES if n == company), company)
    faq = "".join(f"<button name=faq value={k}>{l}</button>" for k, (l, _) in FAQ.items())
    return f"""<main>{_top(("/", "← 公司清單"))}<h1>{escape(label)}</h1><p class=sub>點一個問題</p>
<form id=f><button hidden>查</button><input type=hidden name=company value="{escape(company)}"><div class=faq>{faq}</div>
<h3>或自己輸入問題</h3>{_ask()}</form></main>{_foot()}"""


THIN = 20  # 公開段落少於這個數，才在提示裡明說「公開資料較少」


def _hint(scope, presets, thin, mode="demo"):
    """「我能回答什麼」提示的幾行字：主題、筆數、沒有的資料都由載入的語料算出（job_rag/topics.py）。
    自用模式多一行，明說這些是自用資料（你本機的筆記與面經），並列出面經篇數與私人主題。"""
    t = topics(scope or None, mode=mode)
    ex = "你可以這樣問：" + "".join(f"「{q}」" for _, _, q in presets[:2])
    extra = []
    if mode == "self":
        what = ([f"面經 {t['interviews']} 篇"] if t["interviews"] else []) + t["private_have"]
        extra = ["自用資料（來自你本機的筆記與面經，只在自用模式可查）：" + ("、".join(what) or "目前沒有")]
    if not scope:
        n = len([c for c in public_company_counts(mode=mode) if c != "綜合"])
        return [f"這裡同時搜 {n} 家公司、共 {t['segments']} 段公開資料。", *extra, "沒有的資料：" + "、".join(t["missing"]), ex]
    lines = ["這家有的資料：" + "、".join(t["have"]), *extra, "這家沒有的資料：" + "、".join(t["missing"]), ex]
    if thin and t["segments"] < THIN:
        lines.insert(0, f"這家公開資料較少（只有 {t['segments']} 段），答案可能很短。")
    return lines


@app.get("/c/<label>")
def chat(label):
    """每一家公司（與「全部公司」）各一個對話頁。沒有 JS 時顯示 noscript 裡的伺服器渲染版本。"""
    mode = _mode()
    if _warm["state"] != "ready" or _self_wait(mode):
        return _status_page(mode)
    names = dict(_company_buttons(mode))
    if label != ALL and label not in names:
        return page("找不到", "<main class=status><h1>找不到這家公司</h1><p><a href=\"/\">← 公司清單</a></p></main>"), 404
    scope = "" if label == ALL else names[label]
    hello = (f"我可以回答關於{label}的問題。你可以點下面的題目，或直接問。" if scope
             else "我可以跨公司回答問題。你可以點下面的題目，或直接問。")
    if _owner.enabled:
        hello = f"目前是{owner_ui.LABEL[mode]}模式。" + hello
    presets = _presets(label, mode, scope)
    hint = _hint(scope, presets, PRESETS["companies"].get(label, {}).get("thin"), mode)
    attrs = {"presets": json.dumps(presets, ensure_ascii=False), "hint": json.dumps(hint, ensure_ascii=False), "scope": scope,
             "label": label, "key": label, "hello": hello, "mode": mode}
    data = " ".join(f'data-{k}="{escape(v)}"' for k, v in attrs.items())
    fallback = _company_inner(scope) if scope else _home_inner(mode=mode)
    return page(f"{label}｜求職情報問答", f"""<body class=chat {data}>
<header><a href="/">← 公司清單</a><b class=app>{escape(label)}</b><button id=help type=button aria-label="可以問什麼">？</button><a href="/about">專案說明</a></header>{_chrome(mode)}{_phone_footer()}
<div id=thread role=log aria-live=polite></div>
<form id=bar autocomplete=off><input id=qi name=q placeholder="{escape('例如：' + presets[0][2])}" enterkeyhint=send aria-label="輸入問題"><button class=go>送出</button></form>
<noscript><style>#thread,#bar{{display:none}}</style>{fallback}</noscript><script>{CHAT_JS}</script>""")


@app.get("/")
def index():
    mode = _mode()
    if _warm["state"] != "ready" or _self_wait(mode):
        return _status_page(mode)
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
        return page("求職情報問答", _chrome(mode) + (_company_inner(company) if company and not note else _home_inner(note, mode)))
    link, panel = _eval_panel(q)
    err, ans, status, card, raw, use, raw_open = "", "", 200, "", "", company, True
    try:
        if not use and _on("JOB_RAG_DETECT") and (use := detect_company(q, mode=mode)):
            note += f"<p class='warn'>已偵測到公司：{escape(use)}，只搜這一家。要查全部公司，請把問句裡的公司名拿掉。</p>"
        hits = search(q, company=use, gate=False, dedupe=_on("JOB_RAG_DEDUPE"), mode=mode)  # 預設檢索方式沿用 job_rag；載入模型很慢，只搜一次
        low = _low(hits, use)  # 最高分低於門檻：不呼叫 DeepSeek，原文淡色並展開
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
    clabel = next((l for l, n in _company_buttons(mode) if n == company), company)
    back = [(f"/c/{quote(clabel)}", "← 換問題"), ("/", "← 公司清單")] if company else [("/", "← 換問題")]
    return page("求職情報問答", f"""{_chrome(mode)}<main>{_top(*back)}<p class=q>{escape(q)}</p>
<div id=results>{note}{err}{card}{ans}{details}{script}{link}{panel}</div></main>{_foot()}"""), status


if __name__ == "__main__":
    start_warmup()
    port = int(os.environ.get("JOB_RAG_PORT", "5000"))
    if netinfo.phone_mode():  # 手機模式：對區網開放（僅區網；不做通道或轉發）。印出手機要開的網址
        _phone["cands"] = netinfo.detect()
        print(netinfo.banner(_phone["cands"], port), flush=True)
    app.run(host=netinfo.listen_host(), port=port)

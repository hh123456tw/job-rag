"""/threshold：每一題問了什麼、系統答了什麼，以及拖動「查無門檻」後結果怎麼變。只讀既有評估輸出檔與程式常數，不重算、不呼叫模型。
缺檔、過期、壞檔的來源不畫，頁面註明「缺資料」，不用舊數字。實際答案來自 eval/results_answers.json（eval/run_answers.py 實跑一次的記錄）；
缺檔或題目對不上，卡片就顯示「這題沒有記錄答案」。圖是伺服器畫好的 SVG；JS 只改 class 與文字（一律 textContent）。"""
import hashlib
import json
import math
import re
from pathlib import Path

from markupsafe import escape

from . import about, retrieval
from .evalset import questions_path
from .evaluate import questions_digest
from .ui import page

ROOT = Path(__file__).parent.parent
SL_LO, SL_HI, SL_STEP = 0.40, 0.90, 0.005  # 滑桿範圍（票 35 規格）
# 圖的幾何（viewBox 單位；SVG 寬度 100%，等比縮放）
VW, PAD, R, PITCH, DX = 320, 14, 6, 15, 13
SETS = {"questions": "main", "questions_real": "real", "questions_cross": "cross", "questions_heldout": "held"}  # results_answers.json 的題組名 → 頁面的題組鍵
GROUPS = [("main", "評估題組"), ("real", "真實問法"), ("cross", "跨公司（獨立尺度，固定門檻）"), ("held", "獨立測試題（沒用來調參）")]  # 資料分組（計數用）


class Miss(Exception):
    """某個來源不能用；訊息會顯示在頁面上。"""


def _json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Miss(f"找不到 {rel}") from None
    except (OSError, ValueError) as e:
        raise Miss(f"{rel} 讀不了或格式不對") from e


def _pt(id_, q, s, a, g, sc=False, src=None):
    """k 是頁面用的唯一鍵「題組:題號」（題號在不同題組會重複，例如 u02）。"""
    return {"id": id_, "k": f"{src or g}:{id_}", "q": q, "s": float(s), "a": bool(a), "g": g, "sc": bool(sc)}


def _main(root):
    try:
        qs = _json(root, str(questions_path(root).relative_to(root)))["questions"]
    except (FileNotFoundError, ValueError) as e:
        raise Miss("找不到題目檔") from e
    m = _json(root, "eval/results_methods.json")
    try:
        if m.get("digest") != questions_digest(qs):
            raise Miss("eval/results_methods.json 和現在的題組對不上（過期）")
        b = m["methods"]["bge-m3"]
        scores, scoped = b["gate_scores"], set((b.get("gate") or {}).get("scoped_ids", []))
        by = {q["id"]: q for q in qs}
        if not scores:
            raise Miss("eval/results_methods.json 沒有每題最高分")
        return [_pt(i, by[i]["question"], s, by[i]["answerable"], "main", i in scoped) for i, s in scores.items()]
    except (KeyError, TypeError) as e:
        raise Miss("eval/results_methods.json 格式不對") from e


def _real(root):
    r = _json(root, "eval/results_real.json")
    try:
        qs = _json(root, "eval/questions_real.json")["questions"]
        if r["digest"] != questions_digest(qs):
            raise Miss("eval/results_real.json 和現在的題檔對不上（過期）")
        by = {q["id"]: q for q in qs}
        plain = [_pt(i, by[i]["question"], s, by[i]["answerable"], "real", r["routes"][i] != "跨公司", "real") for i, s in r["scores"].items()]
        cross = [_pt(x["id"], by[x["id"]]["question"], x["top"], x["answerable"], "cross", src="real") for x in r["cross"]]
        return plain, cross
    except (KeyError, TypeError) as e:
        raise Miss("eval/results_real.json 格式不對") from e


def _held(root):
    """獨立測試題（票 39）：點用方形畫。輸出檔不存在就不畫也不算缺資料（舊版或公開版沒有它）；存在但過期或壞掉才算缺資料。"""
    if not (root / "eval/results_heldout.json").exists():
        return []
    r = _json(root, "eval/results_heldout.json")
    try:
        qs = _json(root, "eval/questions_heldout.json")["questions"]
        if r["digest"] != questions_digest(qs):
            raise Miss("eval/results_heldout.json 和現在的題檔對不上（過期）")
        by = {q["id"]: q for q in qs}
        plain = [_pt(i, by[i]["question"], s, by[i]["answerable"], "held", r["routes"][i] != "未指定公司", "held") for i, s in r["scores"].items()]
        cross = [_pt(x["id"], by[x["id"]]["question"], x["top"], x["answerable"], "cross", src="held") for x in r["cross"]]
        return [{**p, "h": True} for p in plain + cross]
    except (KeyError, TypeError) as e:
        raise Miss("eval/results_heldout.json 格式不對") from e


def _cross(root):
    r = _json(root, "eval/results_cross.json")
    try:
        raw = (root / "eval/questions_cross.json").read_bytes()
        if r["digest"] != hashlib.sha1(raw).hexdigest()[:16]:
            raise Miss("eval/results_cross.json 和現在的題檔對不上（過期）")
        by = {q["id"]: q for q in json.loads(raw.decode("utf-8"))["questions"]}
        return [_pt(x["id"], by[x["id"]]["question"], x["top"], x["answerable"], "cross") for x in r["per"][str(r["per_default"])]]
    except (OSError, KeyError, TypeError, ValueError) as e:
        raise Miss("eval/results_cross.json 或題檔格式不對") from e


def load(root=None) -> dict:
    """回 {"pts": 所有點, "miss": {來源名: 原因}}。單一來源失敗只影響它自己，不丟例外。"""
    root = Path(root or ROOT)
    pts, miss = [], {}
    for name, fn, key in (("評估題組", _main, "main"), ("真實問法", _real, "real"), ("跨公司題", _cross, "cross"), ("獨立測試題", _held, "held")):
        try:
            got = fn(root)
        except Miss as e:
            miss[name] = str(e)
            continue
        for part in (got if isinstance(got, tuple) else (got,)):
            pts += part
    return {"pts": pts, "miss": miss, "e2e": about._e2e(root), "held": about._heldout(root), "cards": cards(root, pts)}


def _gold_name(g):
    """金標準來源：公司（檔名去掉編號與副檔名）＋標題。"""
    stem = re.sub(r"^[0-9A-Za-z]{1,2}_", "", g.get("file", "").removesuffix(".md")).replace("_", "／")
    return {"company": stem, "title": g.get("heading", "")}


def cards(root, pts) -> dict:
    """題目卡資料 {題組:題號: {...}}：問題、指定公司、金標準來源，加上實跑記錄（若有且題目文字對得上）。任何來源壞掉只少那一部分。"""
    gold, comp, rels = {}, {}, {"real": "eval/questions_real.json", "cross": "eval/questions_cross.json", "held": "eval/questions_heldout.json"}
    try:
        rels["main"] = str(questions_path(root).relative_to(root))
    except FileNotFoundError:
        pass
    for src, rel in rels.items():
        try:
            for q in _json(root, rel)["questions"]:
                gold[f"{src}:{q['id']}"] = [_gold_name(g) for g in q.get("gold", []) if isinstance(g, dict)]
                comp[f"{src}:{q['id']}"] = q.get("company")
        except (Miss, KeyError, TypeError):
            pass
    try:
        rows = {f"{SETS.get(r['set'])}:{r['id']}": r for r in _json(root, "eval/results_answers.json")["rows"]}
    except (Miss, KeyError, TypeError):
        rows = {}
    try:  # 獨立測試題的答案另存一檔；鍵還是「題組:題號」
        rows |= {f"held:{r['id']}": r for r in _json(root, "eval/results_heldout_answers.json")["rows"]}
    except (Miss, KeyError, TypeError):
        pass
    out = {}
    for p in pts:
        r = rows.get(p["k"])
        if not isinstance(r, dict) or r.get("question") != p["q"]:
            r = None  # 題目對不上（過期）就不用
        out[p["k"]] = {"q": p["q"], "co": comp.get(p["k"]), "gold": gold.get(p["k"], []) if p["a"] else [],
                       "run": r and {"search": r.get("search_status"), "ans_status": r.get("answer_status"), "answer": r.get("answer"),
                                     "det": r.get("detected_company"), "sources": r.get("sources") or [], "date": r.get("date", "")}}
    return out


def thr(p, t, drop, floor):
    """這一題用的門檻：跨公司固定 floor；已指定公司 t − drop；其餘 t。"""
    return floor if p["g"] == "cross" else (t - drop if p["sc"] else t)


def verdict(p, t, drop, floor) -> tuple[bool, bool]:
    """(系統會回答, 處理錯)。最高分低於門檻回查無（和 retrieval 同一個比法）。"""
    ok = p["s"] >= thr(p, t, drop, floor)
    return ok, ok != p["a"]


def counts(pts, t, drop=None, floor=None) -> dict:
    """各組 {答對有答案數 a, 有答案題數 b, 拒答數 c, 沒答案題數 d, 處理錯 n}。"""
    drop = retrieval.SCOPED_DROP if drop is None else drop
    floor = retrieval.CROSS_FLOOR if floor is None else floor
    out = {g: {"a": 0, "b": 0, "c": 0, "d": 0, "n": 0} for g, _ in GROUPS}
    for p in pts:
        ok, wrong = verdict(p, t, drop, floor)
        o = out[p["g"]]
        o["b" if p["a"] else "d"] += 1
        if p["a"] and ok:
            o["a"] += 1
        if not p["a"] and not ok:
            o["c"] += 1
        o["n"] += wrong
    return out


def total(c) -> dict:
    """上方三個數字：評估題組＋真實問法（同一把尺）。跨公司另外算。"""
    return {k: c["main"][k] + c["real"][k] for k in "abcdn"}


def gray_zone(pts):
    """兩類分數重疊的區間 (有答案題的最低分, 沒答案題的最高分)；沒有重疊回 None。只看同一把尺的題。"""
    a = [p["s"] for p in pts if p["g"] not in ("cross", "held") and p["a"]]
    u = [p["s"] for p in pts if p["g"] not in ("cross", "held") and not p["a"]]
    return (min(a), max(u)) if a and u and min(a) <= max(u) else None




def outcome(run):
    """實跑最後結果：擋住（檢索門檻）／查無（答案層）／回答／失敗；沒有記錄回 None。"""
    if not run:
        return None
    if run["search"] == "low":
        return "擋住"
    if run["ans_status"] != "ok":
        return "失敗"
    return "查無" if (run["answer"] or "").strip() == "查無" else "回答"


def badge(p, card, t, drop, floor) -> str:
    """清單用的結果徽章。門檻擋住就是「擋住」；放行後看實跑記錄，沒有記錄就只能說「放行」。"""
    if not verdict(p, t, drop, floor)[0]:
        return "擋住"
    o = outcome((card or {}).get("run"))
    return o if o in ("查無", "回答", "失敗") else "放行"


def _bd(b):
    return f'<span class="t-bd{" b0" if b == "回答" else "" if b in ("擋住", "查無") else " b1"}">{b}</span>'


CSS = """.t-lead{font-size:1.0625rem;margin:0 0 8px}
.t-nums{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}.t-nums div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 6px;text-align:center}
.t-nums b{display:block;font-size:1.75rem;line-height:1.2;color:var(--acc);font-variant-numeric:tabular-nums}.t-nums span{display:block;font-size:.9375rem;line-height:1.4;color:var(--fg)}
.t-ctl{margin:4px 0}.t-ctl .t-vals{display:flex;flex-wrap:wrap;gap:4px 16px;align-items:center;font-variant-numeric:tabular-nums}.t-ctl output{font-weight:650;color:var(--acc)}
input[type=range]{padding:0;border:0;background:none;accent-color:var(--acc);min-height:56px;cursor:pointer;touch-action:pan-y}
input[type=range]::-webkit-slider-thumb{height:32px;width:32px}input[type=range]::-moz-range-thumb{height:32px;width:32px}
.t-btn{min-height:48px;padding:6px 14px;white-space:normal;line-height:1.3}.t-btn[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:var(--on-acc);font-weight:600}
.t-leg{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.9375rem;margin:12px 0 0}.t-leg i{display:inline-block;width:14px;height:14px;border-radius:50%;border:2px solid var(--acc);vertical-align:-2px;margin-right:6px}
.t-leg .on{background:var(--acc)}.t-leg .sq{border-radius:2px}.t-leg .rg{background:none;border-color:var(--err);width:18px;height:18px;vertical-align:-4px;margin-right:4px}
#chart{width:100%;height:auto;display:block;margin:4px 0 8px;-webkit-user-select:none;user-select:none}
#chart text{font:14px system-ui,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;fill:var(--mute)}#chart .rl{fill:var(--fg);font-weight:650}#chart .rl,#chart .lb{paint-order:stroke;stroke:var(--bg);stroke-width:4px;stroke-linejoin:round}
#chart .tk{font-size:13px}#chart .lb{font-weight:700;font-size:17px}#chart .lbt,#chart .lbs{fill:var(--acc)}#chart .lbf{fill:var(--fg)}
#chart .miss{font-style:italic}#chart .ax{stroke:var(--line)}#chart .bl{stroke:var(--line);stroke-dasharray:2 3}
#chart .mv{stroke:var(--acc);stroke-width:2.5}
.pt{cursor:pointer;outline:none}.pt .hz{fill:transparent}.pt .d{fill:var(--acc);stroke:var(--acc);stroke-width:1.5;fill-opacity:.15}.pt.hi .d{fill-opacity:1}
.pt .ring{fill:none;stroke:var(--err);stroke-width:2.5;display:none}.pt.wrong .ring{display:inline}
.gray .pt:not(.on){opacity:.2}.pt.pick .d{stroke:var(--fg);stroke-width:3.5}.pt:focus-visible .d{stroke:var(--fg);stroke-width:3.5}
#card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:8px 0;scroll-margin-top:12px}#card p{margin:6px 0}
#card .cq{font-size:1.125rem;font-weight:650;line-height:1.5}#card .kv{font-size:.9375rem;color:var(--mute)}#card .kv b{color:var(--fg)}
#card .t-ans{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:6px 0;white-space:pre-wrap;line-height:1.65}
#card .t-none{color:var(--mute);font-style:italic}#card ul{margin:4px 0;padding-left:20px;color:var(--mute);font-size:.9375rem}
.t-bd{display:inline-block;border-radius:999px;padding:0 10px;font-size:.9375rem;font-weight:650;border:1.5px solid var(--acc);color:var(--acc);white-space:nowrap}
.t-bd.b0{background:var(--acc);color:var(--on-acc)}.t-bd.b1{border-style:dashed}
#lst>summary{min-height:52px;border:1px solid var(--line);border-radius:10px;padding:0 14px;background:var(--card)}
.t-tools{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.t-rows{list-style:none;padding:0;margin:0}
.t-r{display:block;width:100%;text-align:left;white-space:normal;padding:8px 12px;margin:0;min-height:56px;line-height:1.4}.t-rows li{margin:0 0 8px}.t-r[aria-current=true]{border-color:var(--acc);border-width:2px}
.t-r .t-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.t-r .sc{font-variant-numeric:tabular-nums;font-weight:650;min-width:3.2em}
.t-r .qt{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--mute);margin-top:2px}.t-r .ok{font-size:.9375rem;color:var(--mute)}.t-r .ok.bad{color:var(--err);font-weight:650}
.t-pipe{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;list-style:none;padding:0;margin:8px 0}.t-pipe li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:6px 12px}
.miss-note{color:var(--err);font-size:.9375rem}"""

JS = """<script>(function(){var R=document.getElementById('th'),$=function(x){return document.getElementById(x)},
T=+R.dataset.t,D=+R.dataset.drop,F=+R.dataset.floor,LO=+R.dataset.lo,HI=+R.dataset.hi,L=+R.dataset.l,W=+R.dataset.w,VW=+R.dataset.vw,GZ=R.dataset.gz?R.dataset.gz.split(',').map(Number):null,
C=JSON.parse($('pd').textContent),sl=$('sl'),t=T,filt='all',desc=true,pick=null,
P=[].slice.call(R.querySelectorAll('.pt')).map(function(e){return{e:e,id:e.dataset.id,s:+e.dataset.s,a:e.dataset.a==='1',g:e.dataset.g,sc:e.dataset.sc==='1',h:e.dataset.h==='1'}}),B={};
P.forEach(function(p){B[p.id]=p});
function X(s){return L+(s-LO)/(HI-LO)*W}
function th(p){return p.g==='cross'?F:(p.sc?t-D:t)}
function oc(r){if(!r)return null;if(r.search==='low')return'擋住';if(r.ans_status!=='ok')return'失敗';return(r.answer||'').trim()==='查無'?'查無':'回答'}
function bd(p){if(p.s<th(p))return'擋住';var o=oc((C[p.id]||{}).run);return o==='查無'||o==='回答'||o==='失敗'?o:'放行'}
function gz(p){return GZ!==null&&p.g!=='cross'&&p.s>=GZ[0]&&p.s<=GZ[1]}
function el(tag,cls,txt){var e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function line(id,s){var l=$(id);l.setAttribute('x1',X(s));l.setAttribute('x2',X(s))}
function lab(id,s,txt){var e=$(id),x=X(s),end=x>=VW*.4;e.textContent=txt;e.setAttribute('x',end?x-4:x+4);e.setAttribute('text-anchor',end?'end':'start')}
function badge(p){var b=bd(p);return el('span','t-bd'+(b==='回答'?' b0':b==='擋住'||b==='查無'?'':' b1'),b)}
function show(p){var c=$('card');c.textContent='';if(!p){c.appendChild(el('p','kv','點圖上的點，或打開下面的題目清單，看這題問了什麼、系統答了什麼。'));return}
var d=C[p.id]||{},r=d.run,ok=p.s>=th(p),bad=ok!==p.a;
c.appendChild(el('p','cq',d.q||p.id));
var co=d.co||(r&&r.det)||'',k=el('p','kv');k.appendChild(el('b','',p.a?'語料有答案':'語料沒有答案'));k.appendChild(document.createTextNode('　'+(p.g==='cross'?'跨公司提問':co?'公司：'+co:'沒有指定公司')));c.appendChild(k);
k=el('p','kv');k.appendChild(document.createTextNode('最高相似度 '));k.appendChild(el('b','',p.s.toFixed(3)));k.appendChild(document.createTextNode('　這題的門檻 '));k.appendChild(el('b','',th(p).toFixed(3)));
k.appendChild(document.createTextNode(' → 門檻這一關'+(ok?'放行':'擋住')+'，'));k.appendChild(el('b','',bad?'處理錯':'處理對'));c.appendChild(k);
c.appendChild(el('p','kv','實際答案（'+(r&&r.date?r.date+' 實跑一次，現行門檻':'沒有實跑記錄')+'）'));
if(!r)c.appendChild(el('p','t-none','這題沒有記錄答案。'));
else if(r.search==='low')c.appendChild(el('p','t-none','實跑時檢索門檻就擋住了，沒有產生答案，系統回「查無」。'));
else if(r.ans_status!=='ok')c.appendChild(el('p','t-none','實跑時答案產生失敗（'+(r.ans_status||'無回應')+'），沒有答案可看。'));
else{c.appendChild(el('div','t-ans',r.answer||''));
if((r.answer||'').trim()==='查無')c.appendChild(el('p','kv','檢索放行了，答案層看過段落後回「查無」。'));
else if(r.sources.length){c.appendChild(el('p','kv','答案引用的來源'));var u=el('ul');r.sources.forEach(function(s){u.appendChild(el('li','',s.company+'・'+s.title))});c.appendChild(u)}}
if(d.gold&&d.gold.length){c.appendChild(el('p','kv','題庫標明的答案來源（金標準）'));var g=el('ul');d.gold.forEach(function(s){g.appendChild(el('li','',s.company+'・'+s.title))});c.appendChild(g)}
if(!ok&&r&&r.search!=='low')c.appendChild(el('p','kv','注意：現行門檻下這題會放行；你拖的門檻讓它變成擋住。'))}
function upd(){var S=[0,0,0,0,0];
P.forEach(function(p){var ok=p.s>=th(p),bad=ok!==p.a;if(p.g!=='cross'&&!p.h){S[p.a?1:3]++;if(p.a&&ok)S[0]++;if(!p.a&&!ok)S[2]++;if(bad)S[4]++}
p.e.classList.toggle('hi',ok);p.e.classList.toggle('wrong',bad);p.e.classList.toggle('on',filt!=='gray'||gz(p));p.e.classList.toggle('pick',p===pick)});
$('ca').textContent=S[0]+'/'+S[1];$('cu').textContent=S[2]+'/'+S[3];$('cw').textContent=S[4];
$('tv').textContent=t.toFixed(3);$('ts').textContent=(t-D).toFixed(3);line('l-s',t-D);
lab('lb-s',t-D,'門檻 '+(t-D).toFixed(3));
R.classList.toggle('gray',filt==='gray'&&GZ!==null);
var rows=[].slice.call(R.querySelectorAll('.t-r')),n=0;
rows.sort(function(a,b){return desc?B[b.dataset.id].s-B[a.dataset.id].s:B[a.dataset.id].s-B[b.dataset.id].s});
rows.forEach(function(r){var p=B[r.dataset.id],ok=p.s>=th(p),bad=ok!==p.a,v=filt==='all'||(filt==='wrong'&&bad)||(filt==='gray'&&gz(p)),li=r.parentNode;
li.hidden=!v;if(v)n++;li.parentNode.appendChild(li);
r.querySelector('.t-bd').replaceWith(badge(p));var o=r.querySelector('.ok');o.textContent=bad?'處理錯':'處理對';o.className='ok'+(bad?' bad':'');
r.setAttribute('aria-current',p===pick)});
['all','wrong','gray'].forEach(function(f){$('f-'+f).setAttribute('aria-pressed',filt===f)});$('f-sort').textContent='分數：'+(desc?'高到低':'低到高');
$('lnote').textContent=filt==='gray'?(GZ?'灰色地帶：最高分 '+GZ[0].toFixed(3)+' 到 '+GZ[1].toFixed(3)+' 之間，有答案與沒答案的題混在一起。共 '+n+' 題。':'兩類題的分數沒有重疊，沒有灰色地帶。'):'顯示 '+n+' 題';
show(pick)}
function go(p,list){pick=p;upd();var c=$('card'),b=c.getBoundingClientRect();if(list||b.bottom>innerHeight||b.top<0)c.scrollIntoView({block:list?'start':'nearest',behavior:'smooth'})}
sl.oninput=function(){t=+sl.value;upd()};
$('b-reset').onclick=function(){t=T;sl.value=T;upd()};
['all','wrong','gray'].forEach(function(f){$('f-'+f).onclick=function(){filt=f;upd()}});
$('f-sort').onclick=function(){desc=!desc;upd()};
P.forEach(function(p){function h(){go(p,false)}p.e.onclick=h;p.e.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();h()}}});
[].slice.call(R.querySelectorAll('.t-r')).forEach(function(r){r.onclick=function(){go(B[r.dataset.id],true)}});
upd()})();</script>"""


def _x(s, lo, hi):
    return PAD + (s - lo) / (hi - lo) * (VW - 2 * PAD)


def _lanes(row, lo, hi):
    """同分或很近的點垂直錯開：依分數排序，放進第一條不會碰到前一點的線道。"""
    last, out = [], []
    for p in sorted(row, key=lambda p: p["s"]):
        x = _x(p["s"], lo, hi)
        k = next((i for i, lx in enumerate(last) if x - lx >= DX), len(last))
        if k == len(last):
            last.append(x)
        else:
            last[k] = x
        out.append((p, x, k))
    return out, max(len(last), 1)


def _dot(p, x, y, t, drop, floor):
    shape = f'<rect class=d x=-{R} y=-{R} width={2 * R} height={2 * R} rx=1.5 />' if p.get("h") else f'<circle class=d r={R} />'  # 方形＝獨立測試題
    ok, wrong = verdict(p, t, drop, floor)
    cls = "pt on" + (" hi" if ok else "") + (" wrong" if wrong else "")
    lab = f"{p['id']} 最高分 {p['s']:.3f}"
    return (f'<g class="{cls}" tabindex=0 role=button aria-label="{escape(lab)}" data-id="{escape(p["k"])}" data-s="{p["s"]!r}" '
            f'data-a={int(p["a"])} data-g={p["g"]} data-sc={int(p["sc"])} data-h={int(bool(p.get("h")))} transform="translate({x:.1f} {y:.1f})">'
            f'<circle class=hz r=9 /><circle class=ring r=9.5 />{shape}</g>')


MISS_OF = {"top": ("評估題組", "真實問法", "獨立測試題"), "cross": ("跨公司題", "真實問法", "獨立測試題")}  # 各列的點來自哪些來源
ROWS = (("有答案的題", "top", lambda p: p["g"] != "cross" and p["a"]), ("語料沒有答案的題", "top", lambda p: p["g"] != "cross" and not p["a"]),
        ("跨公司題", "cross", lambda p: p["g"] == "cross"))
HEAD = 28  # 圖頂留給門檻文字的高度


def _chart(pts, miss, lo, hi, t, drop, floor):
    parts, y, ends = [], float(HEAD), []
    for title, src, f in ROWS:
        row = [p for p in pts if f(p)]
        lane, n = _lanes(row, lo, hi)
        parts.append(f'<text x={PAD} y={y + 14} class=rl>{escape(f"{title}（{len(row)} 題）")}</text>')
        y += 22
        if not row:
            why = [f"{k}：{v}" for k, v in miss.items() if k in MISS_OF[src]]
            parts.append(f'<text x={PAD} y={y + 10} class=miss>{escape("缺資料：" + "；".join(why) if why else "沒有這類題")}</text>')
            y += 24
        else:
            for p, x, k in lane:
                parts.append(_dot(p, x, y + R + 3 + k * PITCH, t, drop, floor))
            y += 2 * R + 6 + (n - 1) * PITCH
        ends.append(y)
        parts.append(f'<line class=bl x1={PAD} x2={VW - PAD} y1={y + 3} y2={y + 3} />')
        y += 10
    x = _x(t - drop, lo, hi)  # 只畫一根線：已指定公司用的門檻；未指定（高 drop）與跨公司（固定 floor）改在圖下用文字說明，各點的算法不變
    lines = (f'<line id=l-s class=mv x1={x:.1f} x2={x:.1f} y1={HEAD - 6} y2={ends[1]} />'
             '<text class="lb lbs" id=lb-s y=17 />')
    ticks = "".join(f'<line class=ax x1={_x(v, lo, hi):.1f} x2={_x(v, lo, hi):.1f} y1={y} y2={y + 4} />'
                    f'<text class=tk x={_x(v, lo, hi):.1f} y={y + 18} text-anchor=middle>{v:.1f}</text>'
                    for v in [round(lo + 0.1 * i, 1) for i in range(int((hi - lo) / 0.1 + 1e-9) + 1)])
    h = y + 40
    return (f'<svg id=chart viewBox="0 0 {VW} {h:.0f}" role=img aria-label="每題最高相似度，依題型分三列">{lines}{"".join(parts)}'
            f'<line class=ax x1={PAD} x2={VW - PAD} y1={y} y2={y} />{ticks}'
            f'<text class=tk x={VW / 2} y={h - 4:.0f} text-anchor=middle>檢索第 1 名的相似度（越右越像）</text></svg>')


def _rows(pts, cd, t, drop, floor):
    out = []
    for p in sorted(pts, key=lambda p: -p["s"]):
        wrong = verdict(p, t, drop, floor)[1]
        out.append(f'<li><button type=button class=t-r data-id="{escape(p["k"])}"><span class=t-top><span class=sc>{p["s"]:.3f}</span>'
                   f'{_bd(badge(p, cd.get(p["k"]), t, drop, floor))}<span class="ok{" bad" if wrong else ""}">{"處理錯" if wrong else "處理對"}</span></span>'
                   f'<span class=qt>{escape(p["q"])}</span></button></li>')
    return "".join(out)


def _layers(e2e, c, held=None):
    """兩層把關：3 步一行；端到端數字取自 results_endtoend.json；檢索門檻單獨的拒答數由現行常數算。"""
    flow = "<ol class=t-pipe><li>① 檢索門檻：分數太低就回「查無」</li><li>② 答案層：段落沒寫就回「查無」</li><li>回答或查無</li></ol>"
    t = total(c)
    alone = f"<p>只靠第 ① 層（現行門檻）：語料沒有答案的 {t['d']} 題只擋住 {t['c']} 題，擋不乾淨。</p>"
    if e2e:
        end = (f"<p>兩層一起，真 DeepSeek 端到端跑 {e2e['n']} 道沒有答案的題：<b>{e2e['refused']}/{e2e['n']} 拒答</b>"
               f"（{e2e['by_gate']} 題由檢索門檻擋下，{e2e['by_answer_layer']} 題由答案層回「查無」）。"
               "樣本小、同一人出題、只跑一次，只能當方向。</p>")
    else:
        end = "<p class=miss-note>端到端拒答：缺資料（找不到或讀不了 eval/results_endtoend.json）。</p>"
    hx = held and held.get("e2e")
    hl = (f"<p>獨立測試題（沒用來調參）的 {held['n_unanswerable']} 道沒有答案的題：檢索門檻擋住 {held['blocked_u']}，"
          f"端到端拒答 {hx['refused']}/{hx['n']}（拒答＝被門檻擋下，或答案恰為「查無」）。</p>") if hx else ""
    return f"<h2>兩層把關</h2>{flow}{alone}{end}{hl}"


def _held_note(pts, t, drop, floor) -> str:
    """獨立測試題在現行門檻下的結果（固定、不隨滑桿變）：檢索門檻擋下幾題沒答案題、誤擋幾題有答案題。"""
    h = [p for p in pts if p.get("h")]
    if not h:
        return ""
    a = [p for p in h if p["a"]]
    u = [p for p in h if not p["a"]]
    return (f"<p class=mute>方形是獨立測試題（{len(h)} 題，沒用來調參）：現行門檻下，沒答案題檢索擋住 {sum(not verdict(p, t, drop, floor)[0] for p in u)}/{len(u)}，"
            f"有答案題誤擋 {sum(not verdict(p, t, drop, floor)[0] for p in a)}/{len(a)}。這些數字不隨滑桿變，也不算進上面三個數字。</p>")


def render(d: dict) -> str:
    pts, miss, cd = d["pts"], d["miss"], d.get("cards") or {}
    T, drop, floor = retrieval.NOT_FOUND_THRESHOLD, retrieval.SCOPED_DROP, retrieval.CROSS_FLOOR
    lo = min([SL_LO] + [math.floor(p["s"] * 20) / 20 for p in pts])
    hi = max([SL_HI] + [math.ceil(p["s"] * 20) / 20 for p in pts])
    c = counts(pts, T, drop, floor)
    s = total(c)
    gz = gray_zone(pts)
    gzs = ",".join(repr(x) for x in gz) if gz else ""
    sq_leg = "<span><i class=sq></i>方形：獨立測試題</span>" if any(p.get("h") for p in pts) else ""
    miss_html = "".join(f"<p class=miss-note>缺資料：{escape(k)}（{escape(v)}）。這一列不畫，也不用舊數字。</p>" for k, v in miss.items())
    pd = json.dumps(cd, ensure_ascii=False).replace("<", "\\u003c")  # 放進 <script type=application/json>，不讓 </script> 提前結束
    body = f"""<nav><a href="/">問答</a><a href="/about">專案說明</a><b>查無門檻</b></nav>
<h1>查無門檻：每題問了什麼，系統答了什麼</h1>
<p class=t-lead>系統先看問題和語料像不像；分數低於「門檻」就直接回「查無」。點圖上的點，看那一題的問題和實際答案。</p>
<div id=th data-t={T!r} data-drop={drop!r} data-floor={floor!r} data-lo={lo!r} data-hi={hi!r} data-l={PAD} data-w={VW - 2 * PAD} data-vw={VW} data-gz="{gzs}">
<div class=t-nums><div><b id=ca>{s['a']}/{s['b']}</b><span>可回答的題，有回答</span></div><div><b id=cu>{s['c']}/{s['d']}</b><span>沒答案的題，有拒答</span></div><div><b id=cw>{s['n']}</b><span>處理錯的題</span></div></div>
<div class=t-ctl><label for=sl>拖拖看：門檻</label><input id=sl type=range min={SL_LO} max={SL_HI} step={SL_STEP} value={T!r}>
<div class=t-vals><span>門檻 <output id=ts>{T - drop:.3f}</output></span><button id=b-reset class=t-btn type=button>還原</button></div></div>
<div class=t-leg><span><i class=on></i>深色：放行</span><span><i></i>淡色：擋住</span><span><i class=rg></i>紅圈：處理錯</span>{sq_leg}</div>
{_chart(pts, miss, lo, hi, T, drop, floor)}
<p class=mute id=thn>圖上的線是指定公司時用的門檻。沒指定公司的題，門檻比它高 {drop:.3f}（現在是 <output id=tv>{T:.3f}</output>）；跨公司的題固定用 {floor:.3f}，不跟著動。每一點都用自己適用的那個門檻算。</p>
{_held_note(pts, T, drop, floor)}
<div id=card aria-live=polite><p class=kv>點圖上的點，或打開下面的題目清單，看這題問了什麼、系統答了什麼。</p></div>
<details id=lst class=more><summary>題目清單（{len(pts)} 題）</summary>
<div class=t-tools><button id=f-all class=t-btn type=button aria-pressed=true>全部</button><button id=f-wrong class=t-btn type=button aria-pressed=false>處理錯的</button><button id=f-gray class=t-btn type=button aria-pressed=false>灰色地帶</button><button id=f-sort class=t-btn type=button>分數：高到低</button></div>
<p class=mute>「處理錯」只看第 ① 層門檻；放行後答案層回「查無」的題，最後仍會拒答。</p><p class=mute id=lnote aria-live=polite></p><ul class=t-rows>{_rows(pts, cd, T, drop, floor)}</ul></details>
{miss_html}<script type=application/json id=pd>{pd}</script></div>
{_layers(d.get("e2e"), c, d.get("held"))}
<h2>讀這張圖要小心</h2><p class=mute>題目很少，門檻又是用同一批題調的，圖只是讓人看到取捨，不是最佳解。答案是各題實跑一次的結果（單次執行，DeepSeek 可能隨機，再跑一次文字會不同）。</p>
<footer><a href="/about">回專案說明</a></footer>{JS}"""
    return page("查無門檻｜求職情報問答", body, head=f"<style>{CSS}</style>")

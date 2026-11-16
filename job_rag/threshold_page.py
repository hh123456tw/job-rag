"""/threshold：拖動「查無門檻」，看每一題的判斷怎麼變。只讀既有評估輸出檔與程式常數，不重算、不呼叫模型。
缺檔、過期、壞檔的來源不畫，頁面註明「缺資料」，不用舊數字。圖是伺服器畫好的 SVG；JS 只改 class 與數字。"""
import hashlib
import json
import math
from pathlib import Path

from markupsafe import escape

from . import about, retrieval
from .evalset import questions_path
from .evaluate import questions_digest
from .ui import page

ROOT = Path(__file__).parent.parent
SL_LO, SL_HI, SL_STEP = 0.40, 0.90, 0.005  # 滑桿範圍（票 35 規格）
# 圖的幾何（viewBox 單位；SVG 寬度 100%，等比縮放）
VW, PAD, R, PITCH, DX = 360, 14, 5.5, 14, 12
GROUPS = [("main", "評估題組"), ("real", "真實問法"), ("cross", "跨公司（獨立尺度，固定門檻）")]


class Miss(Exception):
    """某個來源不能用；訊息會顯示在頁面上。"""


def _json(root: Path, rel: str):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Miss(f"找不到 {rel}") from None
    except (OSError, ValueError) as e:
        raise Miss(f"{rel} 讀不了或格式不對") from e


def _pt(id_, q, s, a, g, sc=False):
    return {"id": id_, "q": q, "s": float(s), "a": bool(a), "g": g, "sc": bool(sc)}


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
        plain = [_pt(i, by[i]["question"], s, by[i]["answerable"], "real", r["routes"][i] != "跨公司") for i, s in r["scores"].items()]
        cross = [_pt(x["id"], by[x["id"]]["question"], x["top"], x["answerable"], "cross") for x in r["cross"]]
        return plain, cross
    except (KeyError, TypeError) as e:
        raise Miss("eval/results_real.json 格式不對") from e


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
    for name, fn, key in (("評估題組", _main, "main"), ("真實問法", _real, "real"), ("跨公司題", _cross, "cross")):
        try:
            got = fn(root)
        except Miss as e:
            miss[name] = str(e)
            continue
        for part in (got if isinstance(got, tuple) else (got,)):
            pts += part
    return {"pts": pts, "miss": miss, "e2e": about._e2e(root)}


def thr(p, t, drop, floor):
    """這一題用的門檻：跨公司固定 floor；已指定公司 t − drop；其餘 t。"""
    return floor if p["g"] == "cross" else (t - drop if p["sc"] else t)


def verdict(p, t, drop, floor) -> tuple[bool, bool]:
    """(系統會回答, 判斷錯)。最高分低於門檻回查無（和 retrieval 同一個比法）。"""
    ok = p["s"] >= thr(p, t, drop, floor)
    return ok, ok != p["a"]


def counts(pts, t, drop=None, floor=None) -> dict:
    """各組 {答對有答案數 a, 有答案題數 b, 拒答數 c, 沒答案題數 d, 判斷錯 n}。"""
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
    a = [p["s"] for p in pts if p["g"] != "cross" and p["a"]]
    u = [p["s"] for p in pts if p["g"] != "cross" and not p["a"]]
    return (min(a), max(u)) if a and u and min(a) <= max(u) else None


CSS = """.th-lead{font-size:1.0625rem}
.cnts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0}.cnts div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 8px;text-align:center}
.cnts b{display:block;font-size:1.5rem;line-height:1.2;color:var(--acc);font-variant-numeric:tabular-nums}.cnts span{display:block;font-size:.8125rem;line-height:1.4;color:var(--mute)}
.ctl{margin:8px 0 4px}.ctl .vals{display:flex;flex-wrap:wrap;gap:4px 16px;font-variant-numeric:tabular-nums}.ctl output{font-weight:650;color:var(--acc)}
input[type=range]{padding:0;border:0;background:none;accent-color:var(--acc);min-height:56px;cursor:pointer;touch-action:pan-y}
input[type=range]::-webkit-slider-thumb{height:32px;width:32px}input[type=range]::-moz-range-thumb{height:32px;width:32px}
.th-btns{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.th-btns button{white-space:normal;line-height:1.3;padding:6px 8px}
.th-btns button[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:var(--on-acc);font-weight:600}
#chart{width:100%;height:auto;display:block;margin:8px 0;-webkit-user-select:none;user-select:none}
#chart text{font:11px system-ui,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;fill:var(--mute)}#chart .rl{fill:var(--fg);font-weight:600}
#chart .miss{font-style:italic}#chart .ax{stroke:var(--line)}#chart .bl{stroke:var(--line);stroke-dasharray:2 3}
#chart .cur{stroke:var(--mute);stroke-dasharray:4 3}#chart .mv{stroke:var(--acc);stroke-width:2}#chart .mvs{stroke:var(--acc);stroke-width:1.5;stroke-opacity:.6}
#chart .fl{stroke:var(--warn);stroke-width:1.5;stroke-dasharray:4 3}#chart .gz{fill:var(--warn);fill-opacity:.12;display:none}.gray #chart .gz{display:block}
.pt{cursor:pointer;outline:none}.pt .hit{fill:transparent}.pt .d{fill:var(--acc);stroke:var(--acc);stroke-width:1.5;fill-opacity:.18}.pt.hi .d{fill-opacity:1}
.pt.cross .d{fill:var(--warn);stroke:var(--warn)}.pt .ring{fill:none;stroke:var(--err);stroke-width:2;display:none}.showring .pt.wrong .ring{display:inline}
.gray .pt:not(.sel){opacity:.2}.pt.pick .d{stroke:var(--fg);stroke-width:3}.pt:focus-visible .d{stroke:var(--fg);stroke-width:3}
#detail{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-height:5.5em;margin:8px 0}#detail p{margin:4px 0}
.legend{font-size:.875rem;color:var(--mute);display:grid;gap:4px;margin:8px 0}
.sw{display:inline-block;width:12px;height:12px;border-radius:50%;border:1.5px solid var(--acc);vertical-align:-1px;margin-right:6px}.sw.on{background:var(--acc)}.sw.fl{border-color:var(--warn);background:var(--warn)}.sw.rg{border:2px solid var(--err)}
.miss-note{color:var(--err);font-size:.9375rem}"""

JS = """<script>(function(){var R=document.getElementById('th'),$=function(x){return document.getElementById(x)},
T=+R.dataset.t,D=+R.dataset.drop,F=+R.dataset.floor,LO=+R.dataset.lo,HI=+R.dataset.hi,L=+R.dataset.l,W=+R.dataset.w,GZ=R.dataset.gz?R.dataset.gz.split(',').map(Number):null,
sl=$('sl'),t=T,gray=false,pick=null,P=[].slice.call(R.querySelectorAll('.pt')).map(function(e){return{e:e,s:+e.dataset.s,a:e.dataset.a==='1',g:e.dataset.g,sc:e.dataset.sc==='1',q:e.dataset.q,id:e.dataset.id}});
function X(s){return L+(s-LO)/(HI-LO)*W}
function th(p){return p.g==='cross'?F:(p.sc?t-D:t)}
function line(id,s){var l=$(id);if(l){l.setAttribute('x1',X(s));l.setAttribute('x2',X(s))}}
function show(p){var d=$('detail');if(!p){d.innerHTML='<p>點圖上的點，看題目、分數與目前的判斷。</p>';return}
var ok=p.s>=th(p),bad=ok!==p.a;d.innerHTML='';[['',p.q],['最高相似度 '+p.s.toFixed(3)+'；這題用的門檻 '+th(p).toFixed(3),''],
['這題'+(p.a?'有答案':'語料沒有答案')+'；目前系統會'+(ok?'回答':'回「查無」')+'：'+(bad?'判斷錯':'判斷對'),'']].forEach(function(r,i){var e=document.createElement('p');
if(i===0){e.style.fontWeight=600;e.textContent=p.q}else e.textContent=r[0];d.appendChild(e)})}
function upd(){var C={main:[0,0,0,0,0],real:[0,0,0,0,0],cross:[0,0,0,0,0]};
P.forEach(function(p){var ok=p.s>=th(p),bad=ok!==p.a,c=C[p.g];c[p.a?1:3]++;if(p.a&&ok)c[0]++;if(!p.a&&!ok)c[2]++;if(bad)c[4]++;
p.e.classList.toggle('hi',ok);p.e.classList.toggle('wrong',bad);
p.e.classList.toggle('sel',!gray||(GZ!==null&&p.g!=='cross'&&p.s>=GZ[0]&&p.s<=GZ[1]));p.e.classList.toggle('pick',p===pick)});
var s=[0,1,2,3,4].map(function(i){return C.main[i]+C.real[i]});
$('ca').textContent=s[0]+'/'+s[1];$('cu').textContent=s[2]+'/'+s[3];$('cw').textContent=s[4];
['main','real','cross'].forEach(function(g){var e=$('d-'+g);if(e){var c=C[g];e.textContent=c[1]+c[3]?'有答案 '+c[0]+'/'+c[1]+'、沒答案拒答 '+c[2]+'/'+c[3]+'、判斷錯 '+c[4]:''}});
$('tv').textContent=t.toFixed(3);$('ts').textContent=(t-D).toFixed(3);line('l-t',t);line('l-s',t-D);
$('b-gray').setAttribute('aria-pressed',gray);$('gnote').textContent=gray?(GZ?'灰色地帶：最高分 '+GZ[0].toFixed(3)+' 到 '+GZ[1].toFixed(3)+' 之間的題，有答案與沒答案的分數混在一起。':'兩類題的分數沒有重疊，沒有灰色地帶。'):'';
R.classList.toggle('gray',gray&&GZ!==null);show(pick)}
sl.oninput=function(){t=+sl.value;upd()};
$('b-ring').onclick=function(){var on=!R.classList.contains('showring');R.classList.toggle('showring',on);this.setAttribute('aria-pressed',on)};
$('b-gray').onclick=function(){gray=!gray;upd()};
$('b-clear').onclick=function(){gray=false;pick=null;upd()};
$('b-reset').onclick=function(){t=T;sl.value=T;upd()};
P.forEach(function(p){function go(){pick=p;upd()}p.e.onclick=go;p.e.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
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
    ok, wrong = verdict(p, t, drop, floor)
    cls = "pt" + (" cross" if p["g"] == "cross" else "") + (" hi" if ok else "") + (" wrong" if wrong else "") + " sel"
    lab = f"{p['id']} 最高分 {p['s']:.3f}"
    return (f'<g class="{cls}" tabindex=0 role=button aria-label="{escape(lab)}" data-id="{escape(p["id"])}" data-s="{p["s"]!r}" '
            f'data-a={int(p["a"])} data-g={p["g"]} data-sc={int(p["sc"])} data-q="{escape(p["q"])}" transform="translate({x:.1f} {y:.1f})">'
            f'<circle class=hit r=8 /><circle class=ring r=9 /><circle class=d r={R} /></g>')


MISS_OF = {"main": ("評估題組",), "real": ("真實問法",), "cross": ("跨公司題", "真實問法")}  # 各組的點來自哪些來源


def _chart(pts, miss, lo, hi, t, drop, floor):
    parts, y, span = [], 4.0, {}
    for g, title in GROUPS:
        top = y
        if g == "cross":
            parts.append(f'<text x={PAD} y={y + 12} class=rl>{escape(title)}</text>')
            y += 18
        for ans, name in ((True, "有答案的題"), (False, "語料沒有答案的題")):
            row = [p for p in pts if p["g"] == g and p["a"] == ans]
            lane, n = _lanes(row, lo, hi)
            label = f"{name}（{len(row)} 題）" if g == "cross" else f"{title}・{name}（{len(row)} 題）"
            parts.append(f'<text x={PAD} y={y + 12} class=rl>{escape(label)}</text>')
            y += 18
            if not row:
                why = [f"{k}：{v}" for k, v in miss.items() if k in MISS_OF[g]]
                parts.append(f'<text x={PAD} y={y + 8} class=miss>{escape("缺資料：" + "；".join(why) if why else "沒有這類題")}</text>')
                y += 20
            else:
                for p, x, k in lane:
                    parts.append(_dot(p, x, y + R + 2 + k * PITCH, t, drop, floor))
                y += 2 * R + 4 + (n - 1) * PITCH
            parts.append(f'<line class=bl x1={PAD} x2={VW - PAD} y1={y + 3} y2={y + 3} />')
            y += 8
        span[g] = (top, y)
    top, bot = span["main"][0], span["real"][1]
    vl = lambda cls, v, a, b, id_="": f'<line {id_} class={cls} x1={_x(v, lo, hi):.1f} x2={_x(v, lo, hi):.1f} y1={a} y2={b} />'
    cur = retrieval.NOT_FOUND_THRESHOLD
    lines = (f'<rect class=gz id=gz x=0 y={top} width=0 height={bot - top} />' + vl("cur", cur, top, bot) + vl("cur", cur - drop, top, bot)
             + vl("mv", t, top, bot, "id=l-t") + vl("mvs", t - drop, top, bot, "id=l-s") + vl("fl", floor, *span["cross"]))
    ticks = "".join(f'<line class=ax x1={_x(v, lo, hi):.1f} x2={_x(v, lo, hi):.1f} y1={y} y2={y + 4} />'
                    f'<text x={_x(v, lo, hi):.1f} y={y + 15} text-anchor=middle>{v:.1f}</text>'
                    for v in [round(lo + 0.1 * i, 1) for i in range(int((hi - lo) / 0.1 + 1e-9) + 1)])
    h = y + 32
    return (f'<svg id=chart viewBox="0 0 {VW} {h:.0f}" role=img aria-label="每題最高相似度，依題型分列">{lines}{"".join(parts)}'
            f'<line class=ax x1={PAD} x2={VW - PAD} y1={y} y2={y} />{ticks}'
            f'<text x={VW / 2} y={h - 3:.0f} text-anchor=middle>bge-m3 第 1 名相似度</text></svg>')


def _line(c, g):
    o = c[g]
    return f"有答案 {o['a']}/{o['b']}、沒答案拒答 {o['c']}/{o['d']}、判斷錯 {o['n']}" if o["b"] + o["d"] else ""


def _layers(e2e, c):
    """第二段：兩層把關。端到端數字取自 results_endtoend.json；檢索門檻單獨的拒答數由現行常數算。"""
    flow = ("<ol class=pipe><li class=box><b>問題</b><small>使用者問一句</small></li>"
            "<li class=box><b>① 檢索門檻</b><small>最高相似度太低就直接回「查無」，不呼叫生成</small></li>"
            "<li class=box><b>② 答案層</b><small>段落裡沒寫，答案就回「查無」</small></li>"
            "<li class=box><b>回答或查無</b><small>任一層擋下，都是拒答</small></li></ol>")
    t = total(c)
    alone = f"<p>只看第 ① 層（現行門檻）：評估題組與真實問法中，語料沒有答案的 {t['d']} 題只擋住 {t['c']} 題。單獨靠門檻擋不乾淨。</p>"
    if e2e:
        end = (f"<p>兩層一起，真 DeepSeek 端到端跑 {e2e['n']} 道沒有答案的題：<b>{e2e['refused']}/{e2e['n']} 拒答</b>"
               f"（{e2e['by_gate']} 題由檢索門檻擋下，{e2e['by_answer_layer']} 題由答案層回「查無」）。"
               "樣本小、同一人出題、只跑一次，只能當方向。</p>")
    else:
        end = "<p class=miss-note>端到端拒答：缺資料（找不到或讀不了 eval/results_endtoend.json）。</p>"
    return f"<h2>兩層把關</h2>{flow}{alone}{end}"


def render(d: dict) -> str:
    pts, miss = d["pts"], d["miss"]
    T, drop, floor = retrieval.NOT_FOUND_THRESHOLD, retrieval.SCOPED_DROP, retrieval.CROSS_FLOOR
    lo = min([SL_LO] + [math.floor(p["s"] * 20) / 20 for p in pts])
    hi = max([SL_HI] + [math.ceil(p["s"] * 20) / 20 for p in pts])
    c = counts(pts, T, drop, floor)
    s = total(c)
    gz = gray_zone(pts)
    gzs = ",".join(repr(x) for x in gz) if gz else ""
    miss_html = "".join(f"<p class=miss-note>缺資料：{escape(k)}（{escape(v)}）。這一列不畫，也不用舊數字。</p>" for k, v in miss.items())
    names = {"main": "評估題組", "real": "真實問法", "cross": f"跨公司（固定門檻 {floor:.3f}）"}
    det = "".join(f"<p class=mute>{names[g]}：<span id=d-{g}>{escape(_line(c, g))}</span></p>" for g, _ in GROUPS)
    body = f"""<nav><a href="/">問答</a><a href="/about">專案說明</a><b>查無門檻</b></nav>
<h1>查無門檻：拖拖看</h1>
<p class=th-lead>門檻決定多低的分數要回「找不到」。太高會誤擋有答案的題，太低會讓沒答案的題進入生成。</p>
<div id=th class=showring data-t={T!r} data-drop={drop!r} data-floor={floor!r} data-lo={lo!r} data-hi={hi!r} data-l={PAD} data-w={VW - 2 * PAD} data-gz="{gzs}">
<div class=cnts><div><b id=ca>{s['a']}/{s['b']}</b><span>可回答題有回答</span></div><div><b id=cu>{s['c']}/{s['d']}</b><span>語料沒有答案的題有拒答</span></div><div><b id=cw>{s['n']}</b><span>判斷錯的題數</span></div></div>
<div class=ctl><label for=sl>門檻</label><input id=sl type=range min={SL_LO} max={SL_HI} step={SL_STEP} value={T!r}>
<div class=vals><span>未指定公司 <output id=tv>{T:.3f}</output></span><span>已指定公司 <output id=ts>{T - drop:.3f}</output></span></div></div>
<div class=th-btns><button id=b-gray type=button aria-pressed=false>僅選灰色地帶</button><button id=b-ring type=button aria-pressed=true>圈出判斷錯的題</button>
<button id=b-clear type=button>清除選取</button><button id=b-reset type=button>門檻還原</button></div>
<p class=mute id=gnote aria-live=polite></p>
{_chart(pts, miss, lo, hi, T, drop, floor)}
<div id=detail aria-live=polite><p>點圖上的點，看題目、分數與目前的判斷。</p></div>
<div class=legend><span><i class="sw on"></i>深色點：高於門檻，系統會回答</span><span><i class=sw></i>淡色點：低於門檻，回「查無」</span>
<span><i class="sw rg"></i>紅圈：判斷錯（有答案卻被擋，或沒答案卻放行）</span><span><i class="sw fl"></i>黃色點：跨公司題，用固定的 {floor:.3f}，不跟滑桿動</span>
<span>灰色虛線：程式現行值 {T:.3f}（未指定公司）與 {T - drop:.3f}（已指定公司，低 {drop:.3f}）；藍色實線是你拖的門檻，已指定公司的題用較低那條。</span></div>
{det}{miss_html}</div>
{_layers(d.get("e2e"), c)}
<h2>讀這張圖要小心</h2><p class=mute>題目很少，門檻又是用同一批題調的，圖只是讓人看到取捨，不是最佳解。分數是 bge-m3 的第 1 名相似度。</p>
<footer><a href="/about">回專案說明</a></footer>{JS}"""
    return page("查無門檻｜求職情報問答", body, head=f"<style>{CSS}</style>")

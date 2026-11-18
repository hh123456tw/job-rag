"""/about 的簡報版：一頁一句主張、一張主圖。圖是伺服器畫好的內嵌 SVG／HTML，不載外部函式庫；JS 只換頁。
數字全部來自 about.load() 的輸出與程式常數；缺資料的圖或頁直接略過（缺的是什麼寫在頁面上或回傳的錯誤裡），不用舊數字。
每個圖元素帶 data-v（原始數值），tests/test_about_slides.py 用它對照輸出檔。"""
import statistics

from markupsafe import escape

from . import METHODS, retrieval
from .about_page import CITE_NOTE, CROSS_NOTE, GEN_NOTE, HYBRID, SHORT, _e2e, _hybrid_held, _hybrid_why, _rerank_why, _f, _held_gen, _say, _speech, _sweep_line, hist
from .ui import page

W = 340  # 圖的 viewBox 寬；手機約 1:1，桌面等比放大
INK = "sv"  # SVG 的樣式前綴（見 CSS）


def _t(x, y, s, cls="", anchor="start"):
    return f'<text x="{float(x):g}" y="{float(y):g}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'


def _svg(h, label, body, defs=""):
    return (f'<svg class="{INK}" viewBox="0 0 {W} {h:g}" role="img" aria-label="{escape(label)}">{defs}{body}</svg>')


def _short(name, n=6):
    return name if len(name) <= n else name[: n - 1] + "…"


def _mlab(x, y, method, hot, dy=15):
    """方法名稱的列標籤。混合要寫出混的是哪兩個，所以拆成兩行（名稱＋小字括號），不溢出。"""
    cls = "bd" if hot else ""
    if method == "hybrid":
        return _t(x, y + dy - 6, "混合", cls) + _t(x, y + dy + 6, HYBRID[2:], "xs")
    return _t(x, y + dy, SHORT[method], cls)


def _ticks_h(x0, x1, y, vals, fmt):
    """橫向數值軸（x 軸）：刻度線與數字。"""
    return "".join(f'<line class="ax" x1="{x0 + v * (x1 - x0):.1f}" x2="{x0 + v * (x1 - x0):.1f}" y1="{y}" y2="{y + 4}"/>'
                   + _t(f"{x0 + v * (x1 - x0):.1f}", y + 16, fmt(v), "mu sm", "middle") for v in vals)


# ---------- 各頁 ----------
def s_cover(d, n_segments, n_companies):
    nums = [(n_companies, "家公司"), (n_segments, "段公開事實")]
    if d:
        nums.append((d["n_answerable"] + d["n_unanswerable"], "道評估題"))
    big = "".join(f'<div class="bn"><b data-v="{v}">{v}</b><span>{escape(t)}</span></div>' for v, t in nums)
    fig = f'<div class="bigs">{big}</div>'
    notes = '<p>點一家公司就能問，原文與出處都在旁邊。</p><p class="hint">左右滑動、按鈕或左右鍵翻頁。</p>'
    return "問一句，答案附出處", fig, notes, "cover", "求職情報問答"


def s_arch(d, n_segments, n_companies):
    r = retrieval
    main = [("公開資料", f"{n_companies} 家、{n_segments} 段", 0), ("切段", f"約 {r.CHUNK} 字", 0), ("向量", r.DEFAULT_METHOD, 0),
            ("索引", "FAISS", 0), (f"取前 K 段", f"K = {r.DEFAULT_K}", 0), ("查無門檻", f"低於 {r.NOT_FOUND_THRESHOLD - r.SCOPED_DROP:.3f} 就停", 0),
            ("生成", "DeepSeek", 1), ("答案＋出處", "附引用編號", 0)]
    bw, bh, gx, ys = 100, 54, 120, (8, 94, 180)
    pos = []  # snake：第 1 列左到右、第 2 列右到左、第 3 列左到右
    for i in range(len(main)):
        row, c = divmod(i, 3)
        pos.append((gx * (2 - c if row == 1 else c), ys[row]))
    parts = []
    for i, ((t, sub, hot), (x, y)) in enumerate(zip(main, pos)):
        parts.append(f'<g class="nd{" hot" if hot else ""}"><rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="9"/>'
                     + _t(x + bw / 2, y + 23, t, "bd", "middle") + _t(x + bw / 2, y + 41, sub, "sm", "middle") + "</g>")
        if i:
            (px, py), arrow = pos[i - 1], None
            if py == y:  # 同列水平箭頭
                a, b = (px + bw, x) if x > px else (px, x + bw)
                arrow = f'<line class="ln" x1="{a}" y1="{y + bh / 2}" x2="{b}" y2="{y + bh / 2}" marker-end="url(#ah)"/>'
            else:  # 換列：從上一格底部往下
                arrow = f'<line class="ln" x1="{px + bw / 2}" y1="{py + bh}" x2="{x + bw / 2}" y2="{y}" marker-end="url(#ah)"/>'
            parts.append(arrow)
    ev = [("評估題", ""), ("MRR／Hit@k", ""), ("RAGAS", ""), ("逐句複查", "")]  # 不寫模型名：評審換過（DeepSeek → GPT → Sonnet 5.5），細節在「答案有依據」那頁
    ew, eg, ey = 72, 52 / 3, 276
    parts.append(_t(0, 262, "評估迴路（離線跑，量找法與答案）", "mu bd sm"))
    for i, (t, _) in enumerate(ev):
        x = i * (ew + eg)
        parts.append(f'<rect class="ev" x="{x}" y="{ey}" width="{ew}" height="32" rx="16"/>' + _t(x + ew / 2, ey + 20, t, "sm", "middle"))
        if i:
            parts.append(f'<line class="ln" x1="{x - eg}" y1="{ey + 16}" x2="{x}" y2="{ey + 16}" marker-end="url(#ah)"/>')
    defs = '<defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" class="ar"/></marker></defs>'
    fig = _svg(318, "系統架構：從公開資料到答案與出處，另有評估迴路", "".join(parts), defs)
    notes = ("<p><span class=key></span>實心藍色是唯一會連網的一步；其餘都在本機。</p>"
             f"<p>最高相似度低於門檻就不呼叫 DeepSeek：問一家公司 {r.NOT_FOUND_THRESHOLD - r.SCOPED_DROP:.3f}；"
             f"其他（沒提公司，或提到兩家以上）每家各取 {r.PER_COMPANY} 段、門檻 {r.CROSS_FLOOR:.2f}，提到兩家以上就只查那幾家。<br>{CITE_NOTE}</p>")
    # 先講有兩條檢索路徑；下面的圖畫的是「問一家公司」那條
    paths = ('<div class="qk"><p>下圖是<b>問一家公司</b>的流程。問全部公司另有一條路，見「問全部公司」那頁。</p></div>')
    return f"一個問題，走過 {len(main)} 步", paths + fig, notes, "arch", None


def s_chunk(d, lengths):
    if not lengths:
        return None
    bins = hist(lengths)
    top = max(n for _, n in bins) or 1
    nice = max(top, 1)
    x0, x1, y0, y1 = 34, W - 4, 26, 190  # 繪圖區；y0 是最大值，y1 是 0
    slot = (x1 - x0) / len(bins)
    parts = []
    for v in (0, nice / 2, nice):
        y = y1 - (y1 - y0) * v / nice
        parts.append(f'<line class="gl" x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}"/>' + _t(x0 - 6, y + 4, f"{v:g}", "mu sm", "end"))
    for i, (lab, n) in enumerate(bins):
        h = (y1 - y0) * n / nice
        cx = x0 + slot * (i + 0.5)
        parts.append(f'<rect class="bar gy" data-v="{n}" x="{cx - 17:.1f}" y="{y1 - h:.1f}" width="34" height="{h:.1f}" rx="4"/>'
                     + _t(f"{cx:.1f}", y1 - h - 5, str(n), "bd sm", "middle")
                     + _t(f"{cx:.1f}", y1 + 15, lab.replace(" 字以上", "+").replace(" 字", ""), "xs", "middle"))
    parts.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{y1}" y2="{y1}"/>' + _t((x0 + x1) / 2, y1 + 32, "段落字數（不含前面加的公司名與標題）", "mu sm", "middle")
                 + _t(0, 8, "段數", "mu sm"))
    fig = _svg(228, "切段長度分佈：各字數區間的段數", "".join(parts))
    notes = (f"<p>先依標題切；太長的再切成約 {retrieval.CHUNK} 字、重疊 {retrieval.OVERLAP} 字。</p>"
             f"<p>平均 {statistics.mean(lengths):.0f} 字、中位數 {statistics.median(lengths):.0f} 字、最長 {max(lengths)} 字。{escape(_sweep_line(d))}</p>")
    return f"{len(lengths)} 段，中位數 {statistics.median(lengths):.0f} 字", fig, notes, "chunk", None


def s_methods(d):
    rows = sorted(d["table"], key=lambda r: -r["mrr"])
    best = rows[0]
    # 圖 A：MRR 與 95% 區間
    lx, x0, x1, pitch, y0 = 0, 104, 292, 32, 8
    a = []
    for i, r in enumerate(rows):
        y = y0 + i * pitch
        lo, hi = r["ci"]["mrr"]
        sx = lambda v: x0 + v * (x1 - x0)
        hot = r["method"] == "bge-m3"
        a.append(_mlab(lx, y, r["method"], hot)
                 + f'<rect class="bar gx{"" if hot else " g"}" data-m="{r["method"]}" data-v="{r["mrr"]!r}" data-lo="{lo!r}" data-hi="{hi!r}" x="{x0}" y="{y}" width="{r["mrr"] * (x1 - x0):.1f}" height="20" rx="4"/>'
                 + f'<g class="eb"><line class="h" x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y + 10}" y2="{y + 10}"/><line class="h" x1="{sx(lo):.1f}" x2="{sx(lo):.1f}" y1="{y + 4}" y2="{y + 16}"/>'
                 f'<line class="h" x1="{sx(hi):.1f}" x2="{sx(hi):.1f}" y1="{y + 4}" y2="{y + 16}"/>'
                 f'<line class="c" x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y + 10}" y2="{y + 10}"/><line class="c" x1="{sx(lo):.1f}" x2="{sx(lo):.1f}" y1="{y + 4}" y2="{y + 16}"/>'
                 f'<line class="c" x1="{sx(hi):.1f}" x2="{sx(hi):.1f}" y1="{y + 4}" y2="{y + 16}"/></g>'
                 + _t(x1 + 8, y + 15, _f(r["mrr"]), "bd sm"))
    ya = y0 + len(rows) * pitch
    a.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{ya}" y2="{ya}"/>' + _ticks_h(x0, x1, ya, (0, .25, .5, .75, 1), lambda v: f"{v:g}")
             + _t(x0, ya + 34, "MRR（越高越好）；黑線是 95% 區間", "mu sm"))
    A = _svg(ya + 42, "各找法的 MRR 與 95% 區間", "".join(a))
    # 圖 B：Hit@1／3／5
    pitch2, bh = 44, 9
    b = [f'<rect class="sw h1" x="{x0}" y="0" width="10" height="10"/>' + _t(x0 + 14, 9, "Hit@1", "sm")
         + f'<rect class="sw h3" x="{x0 + 62}" y="0" width="10" height="10"/>' + _t(x0 + 76, 9, "Hit@3", "sm")
         + f'<rect class="sw h5" x="{x0 + 124}" y="0" width="10" height="10"/>' + _t(x0 + 138, 9, "Hit@5", "sm")]
    for i, r in enumerate(rows):
        y = 20 + i * pitch2
        hot = r["method"] == "bge-m3"
        b.append(_mlab(lx, y, r["method"], hot, 17))
        for j, k in enumerate(("hit@1", "hit@3", "hit@5")):
            yy = y + j * (bh + 2)
            b.append(f'<rect class="bar gx h{k[-1]}" data-m="{r["method"]}" data-k="{k}" data-v="{r[k]!r}" x="{x0}" y="{yy}" width="{max(r[k] * (x1 - x0), 0.5):.1f}" height="{bh}" rx="2"/>'
                     + _t(x0 + r[k] * (x1 - x0) + 5, yy + 8, f"{r[k]:.2f}", "xs"))
    yb = 20 + len(rows) * pitch2
    b.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>' + _ticks_h(x0, x1, yb, (0, .25, .5, .75, 1), lambda v: f"{v:g}")
             + _t(x0, yb + 34, f"Hit@k：正確段落排進前 k 名的比例（共 {d['n_answerable']} 題）", "mu sm"))
    B = _svg(yb + 42, "各找法的 Hit@1、Hit@3、Hit@5", "".join(b))
    fig = f'<div class="two"><figure><figcaption>MRR（含 95% 區間；網站用 {retrieval.DEFAULT_METHOD}）</figcaption>{A}</figure><figure><figcaption>Hit@1／3／5</figcaption>{B}</figure></div>'
    m3 = next(r for r in rows if r["method"] == "bge-m3")
    notes = (f"<p>Hit@3＝正確答案的那段，有排進前 3 名的題數比例（Hit@1 是第 1 名、Hit@5 是前 5 名）。"
             f"例：{d['n_answerable']} 題裡有 {m3['found']} 題前 3 名找到，Hit@3＝{m3['hit@3']:.2f}（{m3['found']}/{d['n_answerable']}）。</p>"
             "<p>MRR＝正確段落名次的倒數平均（第 1 名 1 分、第 2 名 0.5 分），沒辦法寫成題數；區間重疊的差距只能當方向。"
             "<br>這頁只比「問一家公司」的找法。問全部公司另有一條路，見「問全部公司」那頁。</p>")
    head = f"{len(METHODS)} 種找法，{SHORT[best['method']]} 最高" if best["method"] == "bge-m3" else f"{len(METHODS)} 種找法比一比"
    return head, fig, notes, "methods", None


def s_held(d):
    """調參用 30 題對調完才測的 100 題（bge-m3，Hit@3 與 MRR，含 95% 區間）。缺任一邊的輸出就略過這頁。"""
    x = d.get("held")
    m3 = next((r for r in d["table"] if r["method"] == "bge-m3"), None)
    if not x or not m3:
        return None
    x0, x1, pitch, y0 = 56, 280, 82, 14
    rows = [("Hit@3", m3["hit@3"], m3["ci"]["hit@3"], x["hit3"], x["hit3_ci"]), ("MRR", m3["mrr"], m3["ci"]["mrr"], x["mrr"], x["mrr_ci"])]
    ns = (d["n_answerable"], x["n_plain_answerable"])  # 兩組各自算 Hit@3 的題數
    shown = lambda name, v, j: f"{v:.2f}（{round(v * ns[j])}/{ns[j]}）" if name == "Hit@3" else _f(v)
    g = []
    for i, (name, v1, c1, v2, c2) in enumerate(rows):
        y = y0 + i * pitch
        g.append(_t(0, y + 4, name, "bd"))
        for j, (lab, v, ci, hot) in enumerate((("30 題", v1, c1, False), (f"{x['n']} 題", v2, c2, True))):
            yy = y + 12 + j * 26
            sx = lambda t: x0 + t * (x1 - x0)
            g.append(_t(x0 - 6, yy + 14, lab, "sm", "end")
                     + f'<rect class="bar gx{"" if hot else " g"}" data-set="{lab}" data-k="{name}" data-v="{v!r}" x="{x0}" y="{yy}" width="{v * (x1 - x0):.1f}" height="20" rx="4"/>'
                     + f'<g class="eb"><line class="h" x1="{sx(ci[0]):.1f}" x2="{sx(ci[1]):.1f}" y1="{yy + 10}" y2="{yy + 10}"/><line class="c" x1="{sx(ci[0]):.1f}" x2="{sx(ci[1]):.1f}" y1="{yy + 10}" y2="{yy + 10}"/></g>'
                     + _t(x1 + 8, yy + 15, shown(name, v, j), "bd sm"))
    ya = y0 + len(rows) * pitch
    g.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{ya}" y2="{ya}"/>' + _ticks_h(x0, x1, ya, (0, .25, .5, .75, 1), lambda v: f"{v:g}")
             + _t(x0, ya + 34, "黑線是 95% 區間", "mu sm"))
    fig = _svg(ya + 42, f"調參用 30 題與調完才測 {x['n']} 題的 Hit@3 與 MRR", "".join(g))
    e = f"；端到端拒答 {x['e2e']['refused']}/{x['e2e']['n']}" if x["e2e"] else ""
    head = f"調完請 Codex 出題 {x['n']} 題"
    bt = x.get("by_type") or {}
    weak = "職缺清單題比單一公司題弱，是已知弱點。" if bt.get("職缺") and bt.get("單一公司") and bt["職缺"]["hit@3"] < bt["單一公司"]["hit@3"] else ""
    parts = "；".join(f"{t} {v['n']} 題 Hit@3 {_f(v['hit@3'])}、MRR {_f(v['mrr'])}" for t, v in bt.items())
    notes = (f"<p><b>為什麼分兩組</b></p><p>・30 題：調參數時一直看它，分數偏高。<br>・{x['n']} 題：調完才測，沒拿來調任何東西，較接近真實程度。<br>・{x['n']} 題由 GPT 出，不是我出的。</p>"
             f"<p><b>怎麼讀圖</b></p><p>・Hit@3：正確那段有沒有進前 3 名，越接近 1 越好；括號是題數。<br>・MRR：正確那段排第幾，越前面越高。<br>・黑線重疊：差距看不出來。</p>"
             + (f"<p><b>分題型</b></p><p>" + "<br>".join(f"・{escape(t)}：Hit@3 {v['hit@3']:.2f}（{round(v['hit@3'] * v['n'])}/{v['n']}）" for t, v in bt.items()) + f"<br>・沒答案 {x['n_unanswerable']} 題：端到端拒答 {x['e2e']['refused']}/{x['e2e']['n']}" * bool(x["e2e"]) + "</p>" if bt else "")
             + f"<p><b>限制</b>：{x['n']} 題由單一模型出、標準答案沒人工確認，只能當方向。{weak}</p>")
    return head, fig, notes, "held", f"30 題對 {x['n']} 題"


def s_score(d):
    """100 題分題型一眼看：每種題一條橫條（0～1），綠＝好、黃＝普通、紅＝弱。缺資料就略過。"""
    x = d.get("held")
    bt = (x or {}).get("by_type") or {}
    if not x or not bt:
        return None
    # 標準指標 Hit@3 寫小數，括號補題數（Hit@3 × 題數本來就是整數，round 只去掉浮點誤差）；數數量的（拒答）只寫幾題／幾題
    rows = [(f"{t}　Hit@3（前 3 名找到）", v["hit@3"], f"{v['hit@3']:.2f}（{round(v['hit@3'] * v['n'])}/{v['n']}）", v["n"]) for t, v in bt.items()]
    if x.get("e2e"):
        rows.append(("沒答案　有拒答", x["e2e"]["refused"] / x["e2e"]["n"], f"{x['e2e']['refused']}/{x['e2e']['n']}", x["e2e"]["n"]))
    x0, x1, pitch, y0 = 8, 270, 46, 6
    g = []
    for i, (lab, v, txt, n) in enumerate(rows):
        y = y0 + i * pitch
        cls = "ok" if v >= .9 else ("mid" if v >= .6 else "bad")
        g.append(_t(x0, y + 10, f"{lab}（{n} 題）", "sm")
                 + f'<rect class="bar gx {cls}" data-k="{escape(lab)}" data-v="{v!r}" x="{x0}" y="{y + 16}" width="{max(v, .01) * (x1 - x0):.1f}" height="20" rx="4"/>'
                 + _t(x1 + 8, y + 31, txt, "bd"))
    fig = _svg(y0 + len(rows) * pitch, "100 題分題型成績", "".join(g))
    notes = ("<p>・<b style='color:var(--ok)'>綠</b>：九成以上的題做對。<br>・<b style='color:var(--mid)'>黃</b>：普通。<br>・<b style='color:var(--bad)'>紅</b>：弱，是已知弱點。</p>"
             f"<p>・{x['n']} 題由 GPT 出，標準答案沒人工確認，只能當方向。</p>")
    # 職缺題偏弱的原因放在圖正下方、用正文字級（不藏在小字備註裡）
    if bt.get("職缺") and bt["職缺"]["hit@3"] < .9:
        fig += ('<div class="qk"><p><b>職缺題為什麼比較弱</b>（職缺題較弱的可能原因（我的推論），沒有逐題確認）</p>'
                "<p>1. 問的是條件，不是職稱。例：「哪些職位讓沒經驗的人也能投？」，段落寫的是「工作經歷：不拘」。</p>"
                "<p>2. 同一家公司的職缺段落長得很像，互相競爭。</p>"
                f"<p>3. 答案分散在好幾段，但一次只取前 {retrieval.DEFAULT_K} 段。</p></div>")
    return "哪裡強、哪裡弱", fig, notes, "score", f"{x['n']} 題成績"


_KIND = {"職缺": ("問職缺", "有哪些職缺、要什麼條件"), "單一公司": ("問某一家公司的事實", "資本額、做什麼、技術"),
         "公司頁短問句": ("在公司頁隨口問的短句", "不寫公司名，只問一句"), "跨公司": ("比較多家公司", "哪些公司有…"),
         "不可回答": ("資料裡沒有答案", "正確做法是回「查無」")}


def s_qset(d):
    """這 130 題問什麼：兩組題各題型的題數與一個真實例題。沒有題檔就略過。"""
    q = d.get("qsets")
    if not q:
        return None
    kinds = list(dict.fromkeys([*q["held"]["kinds"], *q["tune"]["kinds"]]))
    rows = []
    for k in kinds:
        name, hint = _KIND.get(k, (k, ""))
        a, b = q["tune"]["kinds"].get(k), q["held"]["kinds"].get(k)
        ex = (b or a)["example"]
        rows.append(f'<div class="qcard"><h3>{escape(name)}</h3>'  # 一種題型一張字卡
                    f'<p class="ct"><span>調參用 {a["n"] if a else 0} 題</span><span>調完才測 {b["n"] if b else 0} 題</span></p>'
                    f'<p>例：「{escape(ex)}」</p>' + (f'<p class="mu">{escape(hint)}</p>' if hint else "") + "</div>")
    fig = f'<div class="qcards">{"".join(rows)}</div>'
    notes = (f"<p>共 {q['tune']['n'] + q['held']['n']} 題，分兩組：</p>"
             f"<p>・調參用 {q['tune']['n']} 題：我一個人出，調門檻、選找法時一直在看。<br>・調完才測 {q['held']['n']} 題：GPT 出，沒拿來調任何東西。</p>"
             "<p>・每題先標好「正確答案在哪一段」，才能算排名。<br>・刻意放「資料裡沒有答案」的題，測它會不會亂編。<br>・標準答案都沒人工確認，只能當方向。</p>")
    return f"這 {q['tune']['n'] + q['held']['n']} 題問什麼", fig, notes, "qset", "題目長什麼樣"


def _sgn(v):
    return f"{v:+.3f}".replace("-", "−")


def _forest(d):
    rows = d["mrr_diffs"]
    lo = min(0, min(r["lo"] for r in rows)) - 0.04
    hi = max(r["hi"] for r in rows) + 0.04
    x0, x1, pitch, y0 = 10, W - 10, 66, 40
    X = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    n = len(rows)
    yb = y0 + n * pitch
    p = [_t(X(0) - 6, 12, "← 對方較好", "mu sm", "end"), _t(X(0) + 6, 12, "bge-m3 較好 →", "mu sm"),
         ]
    for i, r in enumerate(rows):
        y = y0 + i * pitch
        inc = r["lo"] <= 0 <= r["hi"]
        p.append(f'<line class="zero" x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{y + 24}" y2="{y + 48}"/>' + _t(0, y, f"bge-m3 單用 − {SHORT[r['method']]}", "bd halo")
                 + _t(0, y + 16, f"差 {_sgn(r['diff'])}，區間 [{_sgn(r['lo'])}, {_sgn(r['hi'])}]", "sm mu halo")
                 + f'<g class="fr gx2"><line class="ci" x1="{X(r["lo"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{y + 36}" y2="{y + 36}"/>'
                 f'<line class="ci" x1="{X(r["lo"]):.1f}" x2="{X(r["lo"]):.1f}" y1="{y + 30}" y2="{y + 42}"/>'
                 f'<line class="ci" x1="{X(r["hi"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{y + 30}" y2="{y + 42}"/>'
                 f'<circle class="pt{" open" if inc else ""}" data-m="{r["method"]}" data-v="{r["diff"]!r}" data-lo="{r["lo"]!r}" data-hi="{r["hi"]!r}" cx="{X(r["diff"]):.1f}" cy="{y + 36}" r="6"/></g>')
    ticks = [v / 10 for v in range(int(lo * 10) - 1, int(hi * 10) + 2) if lo <= v / 10 <= hi]
    p.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>'
             + "".join(f'<line class="ax" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{yb}" y2="{yb + 4}"/>' + _t(f"{X(v):.1f}", yb + 16, f"{v:g}", "mu sm", "middle") for v in ticks)
             + _t(W / 2, yb + 34, "MRR 的差（bge-m3 單用減對方），含 95% 區間", "mu sm", "middle")
             + f'<circle class="pt" cx="14" cy="{yb + 54}" r="5"/>' + _t(26, yb + 58, "區間不含 0：差距可信", "sm")
             + f'<circle class="pt open" cx="{W / 2 + 10}" cy="{yb + 54}" r="5"/>' + _t(W / 2 + 22, yb + 58, "區間含 0：看不出差距", "sm"))
    fig = _svg(yb + 66, "bge-m3 單用與其他找法的 MRR 差與 95% 區間（森林圖）", "".join(p))
    hy = next(r for r in rows if r["method"] == "hybrid")
    inc = hy["lo"] <= 0 <= hy["hi"]
    what = f"<p><b>{HYBRID}是什麼：</b>BM25（比對關鍵字）與 bge-m3（比對語意）各排一次名次，再用 RRF 把兩個名次合併：兩邊都排前面的段落分數最高。</p>"
    return fig, what + (f"<p>原本以為{HYBRID}會贏；MRR 差的線碰到 0，代表這批題看不出差別。</p>" if inc
                        else f"<p>{HYBRID}與 bge-m3 的 MRR 差，區間不含 0。</p>")


def s_forest(d):
    """第 5 頁：逐題勝平負條（主圖）；區間森林圖收在「看詳細數字」。"""
    rows = d["versus"]
    x0, x1, pitch, y0, bh = 104, W - 8, 42, 30, 28
    pw = x1 - x0
    yl = y0 + len(rows) * pitch + 6
    p = [_t(0, 10, "每列：bge-m3 對該方法，逐題比誰排得比較前", "mu sm"),
         f'<rect class="sg win" x="0" y="{yl}" width="14" height="12" rx="2"/>' + _t(20, yl + 10, "bge-m3 排得比較前", "sm")
         + f'<rect class="sg tie" x="150" y="{yl}" width="14" height="12" rx="2"/>' + _t(170, yl + 10, "排名一樣", "sm")
         + f'<rect class="sg loss" x="240" y="{yl}" width="14" height="12" rx="2"/>' + _t(260, yl + 10, "比較後", "sm")]
    for i, r in enumerate(rows):
        y = y0 + i * pitch
        p.append(_mlab(0, y, r["method"], False, 18))
        x = x0
        for k, word in (("win", "前"), ("tie", "一樣"), ("loss", "後")):
            v, w = r[k], pw * r[k] / r["n"]
            if v:
                lab = f"{v} 題{word}" if w >= 52 else str(v)
                p.append(f'<rect class="sg {k}" data-m="{r["method"]}" data-k="{k}" data-v="{v}" x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bh}"/>'
                         + _t(f"{x + w / 2:.1f}", y + 19, lab, f"sl {k}", "middle"))
            x += w
    defs = '<defs><pattern id="hp2" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2.5" height="6" class="hp"/></pattern></defs>'
    chart = _svg(yl + 22, "bge-m3 對其他四種找法逐題比較：排得比較前、一樣、比較後的題數", "".join(p), defs)
    forest, detail = _forest(d)
    n = rows[0]["n"]
    mostly_tie = all(2 * r["tie"] > n for r in rows)
    wins = all(r["win"] > r["loss"] for r in rows)
    diff = [r["win"] + r["loss"] for r in rows]
    head = "大多數題一樣；有差的題，bge-m3 贏多輸少" if mostly_tie and wins else ("大多數題一樣；有差的題勝負互見" if mostly_tie else "逐題比，看哪邊排得比較前")
    fig = f'<p class="fh">{escape(head)}</p>{chart}'
    notes = (f"<p>有差的題只有 {min(diff)}–{max(diff)} 題（共 {n} 題），題數太少，不能確定誰真的比較好。</p>"
             "<p>完整的信賴區間在「看詳細數字」。</p>")
    more = f'<details class="more"><summary>看詳細數字</summary>{forest}{detail}</details>'
    short = "多數題一樣，bge-m3 贏多輸少" if mostly_tie and wins else ("多數題一樣，勝負互見" if mostly_tie else "逐題比誰排得前")
    return short, fig, notes, "forest", None, more


def _ba(label, b_lab, b, a_lab, a, mark=None, b_pre=""):
    """前→後卡的一側：標籤、大字數值、0–1 的小條（mark：條上的門檻刻度）。"""
    def side(lab, v, cls, pre=""):
        tick = f'<s style="left:{mark * 100:.1f}%"></s>' if mark is not None else ""
        return (f'<div class="sd {cls}"><span>{escape(lab)}</span><b data-v="{v!r}">{pre}{v:.{label}f}</b>'
                f'<i class="tr"><i class="fl" style="width:{v * 100:.1f}%"></i>{tick}</i></div>')
    return side(b_lab, b, "bf", b_pre) + '<div class="arr" aria-hidden="true">→</div>' + side(a_lab, a, "af")


def s_fixes(d):
    by = {r["method"]: r for r in d["table"]}
    bm, m3 = by["bm25"], by["bge-m3"]
    overlap = m3["ci"]["mrr"][0] <= bm["ci"]["mrr"][1]
    cards = [("① 換找法", "MRR", _ba(3, "BM25", bm["mrr"], "bge-m3", m3["mrr"]),
              "兩者的 95% 區間有重疊，只能當方向。" if overlap else "兩者的 95% 區間沒有重疊。")]
    if rf := d["ragas_fix"]:
        cards.append(("② 修評估程式的錯", "RAGAS 忠實度", _ba(3, f"修正前（{rf['first_scored']} 題）", rf["first"], f"修正後（{rf['now_scored']} 題）", rf["now"]),
                      "評審原本沒看到公司名；題組不同，只看方向。"))
    if sf := d["salary_fix"]:
        cards.append(("③ 補上公司名", f"「{sf['q']}」最高相似度",
                      _ba(2, "補丁前", sf["before"], "補丁後", sf["after"], mark=retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP, b_pre="約 "),
                      f"短問句不含公司名，原本低於門檻 {retrieval.NOT_FOUND_THRESHOLD - retrieval.SCOPED_DROP:.3f}（豎線）被擋；補上公司名後過關。"))
    fig = '<div class="fxs">' + "".join(f'<div class="fx"><h3>{escape(t)}<em>{escape(u)}</em></h3><div class="ba">{body}</div><p>{escape(c)}</p></div>'
                                         for t, u, body, c in cards) + "</div>"
    return "三次修正，都看數據", fig, "", "fixes", None


def s_funnel(d, e2e):
    link = '<p class="link"><a class="btn" href="/threshold">查無門檻：自己拖拖看</a></p>'
    if not e2e:
        fig = '<p class="err">缺資料：找不到或讀不了 eval/results_endtoend.json，兩層把關的端到端圖略過。</p>'
        return "兩層把關，沒把握不亂答", fig + link, "<p>① 最高相似度太低，直接回「查無」。② 段落裡沒寫，答案層回「查無」。</p>", "funnel", None
    n, g, ans = e2e["n"], e2e["by_gate"], e2e["by_answer_layer"]
    w0 = 300
    wd = lambda k: w0 * k / n if n else 0
    cx = W / 2
    s1, s2, s3 = n, n - g, n - e2e["refused"]  # 進入各層後仍在的題數；s3 是最後仍回答的題數
    band = lambda y, w, v, cls="": f'<rect class="fb{cls}" data-v="{v}" x="{cx - w / 2:.1f}" y="{y}" width="{max(w, 0):.1f}" height="24" rx="4"/>'
    hat = lambda y, w: f'<rect class="hat" x="{cx - w / 2:.1f}" y="{y}" width="{w:.1f}" height="24" rx="4"/>'
    p = [_t(0, 14, f"問題：語料沒有答案的 {n} 題", "bd"), band(22, wd(s1), s1),
         _t(0, 72, f"① 檢索門檻：擋下 {g} 題，放行 {s2} 題", "bd"), hat(80, wd(s1)), band(80, wd(s2), s2),
         _t(0, 130, f"② 答案層：擋下 {ans} 題，放行 {s3} 題", "bd"), hat(138, wd(s2)), band(138, wd(s3), s3, " z"),
         f'<circle class="dz" cx="{cx}" cy="150" r="{4 if s3 == 0 else 0}"/>',
         f'<rect class="sw hat" x="0" y="178" width="14" height="10"/>' + _t(20, 187, "被擋下（回「查無」）", "sm")
         + f'<rect class="sw fb" x="{W / 2 + 6}" y="178" width="14" height="10"/>' + _t(W / 2 + 26, 187, "繼續往下", "sm")]
    defs = '<defs><pattern id="hp" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2.5" height="6" class="hp"/></pattern></defs>'
    fig = _svg(196, "兩層把關漏斗：問題經檢索門檻與答案層後仍回答的題數", "".join(p), defs)
    big = (f'<div class="e2e"><b data-v="{e2e["refused"]}" data-n="{n}">{e2e["refused"]} / {n}</b>'
           f'<span>沒有答案的題，全部拒答（真 DeepSeek、網站實際路徑，只跑一次）</span></div>')
    notes = "<p>檢索門檻單獨擋不乾淨，要靠答案層補上。答案層靠提示詞：段落沒寫就回「查無」。</p><p>樣本小、同一人出題，只能當方向。</p>"
    # 輸出檢查放在圖下方、用正文字級：它管的是「引用錯編號」，不是「沒答案」，所以不算進上面的兩層與題數
    extra = f'<div class="qk"><p><b>另有一個輸出檢查</b>（管的是別的錯，不算在這 {n} 題裡）</p><p>{CITE_NOTE}</p></div>'
    return f"兩層把關：{e2e['refused']}/{n} 題拒答", f'<div class="two">{fig}{big}</div>{link}{extra}', notes, "funnel", None


def s_cross(d, n_companies, companies):
    """問全部公司：示意圖＋一個主數字（取到幾家／該取到幾家）。簡報裡跨公司只出現在這一頁。沒有數字就只留示意圖。"""
    x = d.get("cross_slide") if d else None
    per = retrieval.PER_COMPANY
    names = list(companies or [])[:n_companies] or [f"公司 {i + 1}" for i in range(n_companies)]
    cols, cw, ch, gap = 4, 76, 54, 12
    p = []
    for i, nm in enumerate(names):
        r, c = divmod(i, cols)
        sx, sy = c * (cw + gap) + (W - cols * cw - (cols - 1) * gap) / 2, r * (ch + gap)
        segs = "".join(f'<rect class="sg" x="{sx + 14 + k * 20:.1f}" y="{sy + 33}" width="16" height="9" rx="2"/>' for k in range(per))
        p.append(f'<rect class="co" x="{sx:.1f}" y="{sy}" width="{cw}" height="{ch}" rx="9"/>' + _t(sx + cw / 2, sy + 21, _short(nm), "bd sm", "middle") + segs)
    h = ((len(names) + cols - 1) // cols) * (ch + gap)
    p.append(_t(W / 2, h + 14, f"每家各取 {per} 段（■）→ 合併 → 交給 DeepSeek 逐家整理", "mu sm", "middle"))
    schem = _svg(h + 24, f"跨公司示意：{len(names)} 家公司各取 {per} 段", "".join(p))
    if not x:
        return f"問全部公司：每家各取 {per} 段", f"<figure>{schem}</figure>", "<p>挑段用混合（BM25＋bge-m3）；要不要拒答，看 bge-m3 的最高分。</p>", "cross", None
    def card(key, title, v):  # 一組題一張卡：混合的取到家數（大字）、MRR，下面一行是只用 bge-m3 的對照
        return (f'<div class="e2e" style="margin-bottom:12px"><span><b class="lab">{title}</b></span>'
                f'<b data-k="{key}" data-v="{v["got"]}" data-n="{v["want"]}">{v["got"]} / {v["want"]}</b>'
                f'<span>混合（網站現行）：該取到的公司，取到幾家</span>'
                f'<p class="mrr">MRR <b data-k="{key}_mrr" data-v="{v["mrr"]!r}">{_f(v["mrr"])}</b></p>'
                f'<i class="tr"><i class="fl" style="width:{100 * v["got"] / v["want"]:.1f}%"></i></i>'
                f'<p class="mu" data-k="{key}_base">只用 bge-m3：{v["base_got"]} / {v["want"]}，MRR {_f(v["base_mrr"])}</p></div>')

    t, v = x["tune"], x["val"]
    big = (card("tune", f"調參用：我自己出的 {t['n']} 題", t)
           + card("val", f"驗證：Codex 出的 {v['n']} 題（直白問法，沒用來調參）", v))
    why = ('<div class="qk" style="margin-top:14px"><p><b>為什麼跨公司用混合</b></p>'
           "<p>跨公司常問技術名詞或職稱，在職缺段落裡只是一個字。向量比的是整段意思，抓不到這種細節。</p>"
           f"<p>所以加了關鍵字比對。在沒用來調參的驗證題上：MRR 從 {v['base_mrr']:.2f} 到 {v['mrr']:.2f}，"
           f"取到的公司從 {v['base_got']} 家到 {v['got']} 家（共 {v['want']} 家）。</p></div>")
    e = x.get("example")
    how = ('<div class="qk"><p><b>怎麼測</b></p>'
           "<p>1. 每題有一個關鍵字。" + (f"例：「{escape(e['q'])}」關鍵字 {escape(e['kw'])}。" if e else "") + "</p>"
           "<p>2. 先用關鍵字掃語料，找出該出現的公司" + (f"（這題 {e['want']} 家）" if e else "") + "。</p>"
           f"<p>3. 再看系統每家取回的 {per} 段裡，有沒有含關鍵字的段落" + (f"（這題取到 {e['got']} 家）" if e else "") + "。</p>"
           "<p>4. 每組題各自加總。被門檻擋掉的題也照算。</p>"
           "<p>5. MRR：每一家該出現的公司，含關鍵字的段落在那一家裡排第幾名，取倒數後平均。</p></div>")
    notes = ("<p>挑段用混合（BM25＋bge-m3）：技術名詞靠字面比對較準。要不要拒答，看 bge-m3 的最高分。</p>"
             f"<p>弱點：短的技術名詞題會被拒答門檻擋掉（驗證 {v['n']} 題裡 {v['blocked']} 題、調參用 {t['n']} 題裡 {t['blocked']} 題）。"
             "這頁只比挑段方式，被擋掉的題也照算。</p>")
    return f"問全部公司：每家各取 {per} 段", f'<div class="two"><div><figure>{schem}</figure>{why}</div><div>{big}{how}</div></div>', notes, "cross", None


def s_ragas(d):
    g, c = d["generation"], d["cross"]
    if not g:
        return None
    gpt = d.get("ragas_gpt")  # 有 GPT 當評審的 RAGAS 就用它；沒有才用 DeepSeek 評審那份
    src = gpt["tune"] if gpt else g
    x0, x1, pitch = 100, 290, 40
    bars = [("忠實度", src["faithfulness"], "faithfulness"), ("答案相關性", src["answer_relevancy"], "answer_relevancy")]
    p = []
    for i, (lab, v, k) in enumerate(bars):
        y = 4 + i * pitch
        p.append(_t(0, y + 17, lab, "bd") + f'<rect class="tk" x="{x0}" y="{y}" width="{x1 - x0}" height="24" rx="5"/>'
                 + f'<rect class="bar gx" data-k="{k}" data-v="{v!r}" x="{x0}" y="{y}" width="{v * (x1 - x0):.1f}" height="24" rx="5"/>'
                 + _t(x1 + 8, y + 17, _f(v), "bd"))
    yb = 4 + len(bars) * pitch
    p.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>' + _ticks_h(x0, x1, yb, (0, .5, 1), lambda v: f"{v:g}")
             + _t(x0, yb + 34, (f"RAGAS（{gpt['judge']} 評審），{src['scored']} 題；滿分 1" if gpt else f"RAGAS（DeepSeek 評，與生成同模型），{g['scored']} 題；滿分 1"), "mu sm"))
    chart = _svg(yb + 42, "RAGAS 忠實度與答案相關性", "".join(p))
    cs = d.get("cross_sonnet")
    who_chk = "Sonnet 5.5" if cs and gpt and gpt["judge"] == "Sonnet 5.5" else "GPT"  # RAGAS 與複查同一個評審才換，避免一頁三種
    if who_chk != "GPT":
        c = cs
    chk = ""
    if c:
        chk = (f'<div class="e2e"><b data-v="{c["supported"]}" data-n="{c["claims"]}">{c["supported"]} / {c["claims"]}</b>'
               f'<span>個說法有依據（{who_chk} 複查，調參用題組 {c["n"]} 題）</span>'
               f'<i class="tr"><i class="fl" style="width:{100 * c["supported"] / c["claims"]:.1f}%"></i></i></div>')
    h = d.get("held_cross_sonnet") if who_chk != "GPT" else d.get("held_cross")
    if c and h:
        chk += (f'<div class="e2e"><b data-v="{h["supported"]}" data-n="{h["claims"]}">{h["supported"]} / {h["claims"]}</b>'
                f'<span>個說法有依據（{who_chk} 複查，獨立測試題 {h["n"]} 題）</span>'
                f'<i class="tr"><i class="fl" style="width:{100 * h["supported"] / h["claims"]:.1f}%"></i></i></div>')
    notes = ("<p>" + "主數字是 GPT 複查：由 Codex CLI 的 GPT 逐句對照段落，不是生成用的 DeepSeek。<br>" * bool(c)
             + f"RAGAS 的評審與生成同為 DeepSeek，同模型自評可能偏樂觀，只當附註。答案相關性沒有 GPT 版本。</p><p>{GEN_NOTE}{_held_gen(d)}</p>")
    if gpt:
        hd = gpt.get("held")
        held = (f"<br>獨立測試題 {hd['scored']} 題：忠實度 {_f(hd['faithfulness'])}、答案相關性 {_f(hd['answer_relevancy'])}。" if hd else "")
        bad = sum(v["failed"] for k, v in gpt.items() if k != "judge")
        who = (f"評審都是 {who_chk}：左邊是逐句複查，右邊是 RAGAS。" if gpt["judge"] == who_chk
               else f"右邊的 RAGAS 由 {gpt['judge']} 評審；左邊的逐句複查由 GPT 做。")
        notes = (f"<p>{who}生成用的是 DeepSeek，評審換了別的模型。" + held + "</p>"
                 "<p>答案和段落沒有重新產生；跨公司改動之後的答案沒有重評。評審只跑一次，輸出有隨機性。"
                 + (f"有 {bad} 題評分失敗，沒有補分。" if bad else "") + "</p>")
    head = (f"GPT 複查：{c['supported']}/{c['claims']} 有依據" if who_chk == "GPT" else f"答案有依據：{c['supported']}/{c['claims']}") if c else f"答案有依據：忠實度 {src['faithfulness']:.2f}"
    return head, f'<div class="two"><div>{chk}</div>{chart}</div>' if c else chart, notes, "ragas", None


def _icon(path):
    return f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">{path}</svg>'


ICONS = {"warn": _icon('<path d="M12 3 2.5 20h19z"/><path d="M12 10v5M12 17.5v.5"/>'),
         "no": _icon('<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>'),
         "up": _icon('<path d="M5 19 19 5M9 5h10v10"/>')}


def s_limits(d):
    na, nu = (d["n_answerable"], d["n_unanswerable"]) if d else (None, None)
    lim = [f"題少：{na} 題有答案、{nu} 題沒答案" if d else "題少", "題目與語料同源" if not (d and d.get("held")) else f"原題與語料同源；另有 {d['held']['n']} 題獨立測試題（單一模型出題、金標未人工確認）", "門檻用同批題挑，偏樂觀", "單機、單一存取碼"]
    rr = bool(d and d.get("held_methods"))  # 重排序量過了就不算「沒做」：改列在限制裡，寫明量過、沒接上
    if rr:
        lim.append("重排序模型：量過，沒接上（看不出差別、每題慢約 7 秒）")
    undone = ([] if rr else ["重排序模型"]) + ["向量資料庫", "微調模型", "線上監控"] + ([] if d and d.get("held") else ["獨立測試題"])
    nxt = ["近似索引，只編新段落", "PDF 與掃描檔解析", "改動後自動重考"]
    col = lambda ic, t, items, tag="": (f'<div class="col"><div class="ch">{ICONS[ic]}<h3>{escape(t)}</h3></div>{f"<em>{escape(tag)}</em>" if tag else ""}'
                                         + "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul></div>")
    fig = ('<div class="cols">' + col("warn", "限制", lim) + col("no", "沒做", undone)
           + col("up", "放大 100 倍，先做", nxt, "設計想法，尚未實作") + "</div>")
    return "限制、沒做的、下一步", fig, "", "limits", None


def _vs_line(d):
    """混合對 bge-m3 的逐題勝平負（講稿與問答備案共用）。"""
    v = next((x for x in d["versus"] if x["method"] == "hybrid"), None) if d else None
    return f"{v['n']} 題裡 {v['tie']} 題排名一樣、{v['win']} 題 bge-m3 排得比較前、{v['loss']} 題比較後；" if v else ""


def _rr_short(d):
    h = d and d.get("held_methods")
    if not h:
        return ""
    v = h["rerank"]
    return (f"量過：獨立題 {h['n']} 題 MRR {_f(h['base_mrr'])} → {_f(v['mrr'])}，"
            + ("區間含 0，看不出差別" if v["lo"] <= 0 <= v["hi"] else "差異可信") + f"；每題約 {v['sec']:.0f} 秒，沒有接上。")


def s_qa(d, n_segments):
    m3 = next((r for r in d["table"] if r["method"] == "bge-m3"), None) if d else None
    df, gt = (d["mrr_diff"], d["gate"]) if d else (None, None)
    rows = [("資料放大 100 倍怎麼辦？", "沒做過；要換近似索引、只編新段落，再重新評估。"),
            ("為什麼不用重排序模型？", (_rr_short(d) + _rerank_why(d, n_segments)) or (f"沒試過；bge-m3 的 MRR 已有 {_f(m3['mrr'])}，加了會不會更好沒量過。" if m3 else "沒試過，也沒量過。")),
            ("為什麼混合（BM25＋bge-m3）沒有贏？",
             (_vs_line(d) + f"MRR 差 {df['diff']:+.3f}，區間 [{df['lo']:+.3f}, {df['hi']:+.3f}]"
              + ("，含 0：差異不大，沒必要加混合（不是證明 bge-m3 較好）。" if df["lo"] <= 0 <= df["hi"] else "，不含 0。")
              + _hybrid_held(d) + _hybrid_why(d)) if df else "這份輸出沒有比較數字。"),
            ("查無門檻是不是太樂觀？",
             "是，門檻用同一批題挑。" + (f"沒有答案的題擋住 {gt['unanswerable_blocked']}/{gt['n_unanswerable']}{_e2e(d)}，有答案的題誤擋 {gt['answerable_blocked']}/{gt['n_answerable']}。" if gt else "")),
            ("沒有向量資料庫，算向量檢索嗎？", f"算；問題與 {n_segments} 段都轉成向量比相似度，用 FAISS 在記憶體內比。")]
    body = "".join(f"<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>" for q, a in rows)
    return "常被追問的 5 題", f'<div class="qa">{body}</div>', "<p>點一題，看一句話答案。</p>", "qa", None


def s_error(error):
    return "評估圖表無法顯示", f'<p class="err">無法顯示：{escape(error)}</p>', "<p>其餘頁面照常顯示；這裡不放舊數字。</p>", "error", None


# ---------- 組頁 ----------
CSS = """body.sl{max-width:900px;padding:0 16px 168px}
.qk{margin:0 0 14px}.qk p{margin:2px 0}
.qcards{display:grid;gap:12px}@media(min-width:760px){.qcards{grid-template-columns:1fr 1fr}}
.qcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.qcard h3{margin:0 0 6px;font-size:1.05rem}.qcard p{margin:4px 0}
.qcard .ct{display:flex;gap:8px;flex-wrap:wrap}.qcard .ct span{border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:.85rem;color:var(--mute)}
.sh{display:flex;align-items:center;justify-content:space-between;min-height:52px;font-size:.9375rem}
.sh a{display:inline-flex;align-items:center;min-height:48px}.sh b{color:var(--mute);font-weight:500}
.slide{padding:0 0 16px}.js .slide{display:none}.js .slide.cur{display:block;animation:fi .25s ease-out}
@keyframes fi{from{opacity:0;transform:translateY(8px)}}
.kick{margin:12px 0 0;font-size:.875rem;font-weight:700;color:var(--acc);letter-spacing:.04em}
.slide h2{font-size:clamp(1.5rem,6vw,2.5rem);line-height:1.25;font-weight:700;margin:6px 0 16px}
.fig{margin:8px 0 12px}.fig figure{margin:0}.fig figcaption{font-size:.9375rem;font-weight:600;color:var(--mute);margin:0 0 4px}
.sv{display:block;width:100%;height:auto;max-width:640px;margin:0 auto;overflow:visible}
.sv text{font:12px/1 system-ui,-apple-system,"Segoe UI","PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;fill:var(--fg)}
.sv .mu{fill:var(--mute)}.sv .sm{font-size:11.5px}.sv .xs{font-size:10.5px;fill:var(--mute)}.sv .bd{font-weight:650}.sv .halo{stroke:var(--bg);stroke-width:5px;paint-order:stroke}
.sv .ax{stroke:var(--mute);stroke-width:1}.sv .gl{stroke:var(--line);stroke-width:1}
.sv .bar{fill:var(--acc)}.sv .bar.g{fill:var(--mute);fill-opacity:.55}.sv .bar.ok{fill:var(--ok)}.sv .bar.mid{fill:var(--mid)}.sv .bar.bad{fill:var(--bad)}
.sv .h1,.sv .h3,.sv .h5{fill:var(--acc);stroke:var(--acc);stroke-width:1}.sv .h1{fill-opacity:.25}.sv .h3{fill-opacity:.55}.sv .h5{fill-opacity:1}
.sv .eb .h{stroke:var(--bg);stroke-width:4.5;stroke-linecap:round}.sv .eb .c{stroke:var(--fg);stroke-width:1.75;stroke-linecap:round}
.sv .tk{fill:var(--card);stroke:var(--line)}
.sv .nd rect{fill:var(--card);stroke:var(--line)}.sv .nd.hot rect{fill:var(--acc);stroke:var(--acc)}.sv .nd.hot text{fill:var(--on-acc)}
.sv .ln{stroke:var(--mute);stroke-width:1.5;fill:none}.sv .ar{fill:var(--mute)}
.sv .ev{fill:none;stroke:var(--mute);stroke-dasharray:4 3}
.sv .zero{stroke:var(--fg);stroke-width:1.25;stroke-dasharray:4 3}.sv .ci{stroke:var(--fg);stroke-width:2;stroke-linecap:round}
.sv .pt{fill:var(--acc);stroke:var(--acc);stroke-width:2}.sv .pt.open{fill:var(--bg)}
.sv .fb{fill:var(--acc)}.sv .hat{fill:url(#hp);stroke:var(--mute);stroke-opacity:.6}.sv .hp{fill:var(--mute);fill-opacity:.6}.sv .dz{fill:var(--acc)}
.sv .co{fill:var(--card);stroke:var(--line)}.sv .sg{fill:var(--acc)}.sv .sw.hat{fill:url(#hp)}
.fh{margin:0 0 8px;font-weight:650;font-size:1.0625rem}
.sv .sg.win{fill:var(--acc)}.sv .sg.tie{fill:url(#hp2);stroke:var(--mute)}.sv .sg.loss{fill:var(--warn)}
.sv .sl{font-size:12px;font-weight:650;fill:var(--fg);paint-order:stroke}.sv .sl.win{fill:var(--on-acc)}.sv .sl.loss{fill:var(--on-warn)}.sv .sl.tie{stroke:var(--bg);stroke-width:4px}
.more{margin-top:12px}.more summary{color:var(--mute);font-weight:500}
.gx{transform-box:fill-box;transform-origin:0 50%}.gy{transform-box:fill-box;transform-origin:50% 100%}.gx2{transform-box:fill-box;transform-origin:50% 50%}
.js .cur .gx{animation:gx .3s ease-out both}.js .cur .gy{animation:gy .3s ease-out both}
@keyframes gx{from{transform:scaleX(0)}}@keyframes gy{from{transform:scaleY(0)}}
.two{display:grid;gap:20px}@media(min-width:760px){.two{grid-template-columns:1fr 1fr;align-items:start}}
.bigs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}
.bn{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 12px}
.bn b{display:block;font-size:clamp(2.25rem,10vw,4rem);line-height:1.1;color:var(--acc);font-variant-numeric:tabular-nums}.bn span{color:var(--mute);font-size:.9375rem}
.hint{color:var(--mute);font-size:.9375rem}
.slide>p,.slide .sn p{margin:6px 0;color:var(--mute);font-size:1rem;line-height:1.55}
.key{display:inline-block;width:12px;height:12px;border-radius:3px;background:var(--acc);margin-right:8px;vertical-align:-1px}
.fxs{display:grid;gap:14px}@media(min-width:760px){.fxs{grid-template-columns:repeat(3,1fr)}}
.fx{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.fx h3{margin:0 0 10px;font-size:1.0625rem;color:var(--fg)}.fx h3 em{display:block;font-style:normal;font-weight:400;font-size:.875rem;color:var(--mute)}
.fx p{margin:10px 0 0;font-size:.9375rem;line-height:1.5;color:var(--mute)}
.ba{display:grid;grid-template-columns:1fr auto 1fr;gap:6px;align-items:center}
.sd span{display:block;font-size:.8125rem;color:var(--mute);line-height:1.3;min-height:2.1em}.sd b{display:block;font-size:1.75rem;line-height:1.2;font-variant-numeric:tabular-nums}
.sd.af b{color:var(--acc)}.arr{font-size:1.5rem;color:var(--acc);font-weight:700}
.tr{display:block;position:relative;height:10px;margin-top:6px;border-radius:5px;background:var(--bg);border:1px solid var(--line);overflow:visible}
.tr .fl{display:block;height:100%;border-radius:4px;background:var(--mute);opacity:.6}.sd.af .fl,.e2e .fl{background:var(--acc);opacity:1}
.tr s{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--fg)}
.e2e{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.e2e b.cmp{color:var(--mute)}.e2e b.lab{display:inline;font-size:1rem;color:inherit}.e2e .mrr{margin:8px 0 6px;font-size:1.05rem}.e2e .mrr b{display:inline;font-size:1.4rem}
.e2e b{display:block;font-size:clamp(2.5rem,11vw,3.5rem);line-height:1.1;color:var(--acc);font-variant-numeric:tabular-nums}.e2e span{color:var(--mute)}
.cols{display:grid;gap:12px}@media(min-width:760px){.cols{grid-template-columns:repeat(3,1fr)}}
.col{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.col .ic{width:28px;height:28px;fill:none;stroke:var(--acc);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.ch{display:flex;align-items:center;gap:10px}.col h3{margin:0;font-size:1.125rem;color:var(--fg)}.col em{display:inline-block;font-style:normal;font-size:.8125rem;color:var(--mute);border:1px dashed var(--mute);border-radius:999px;padding:0 8px;margin-bottom:4px}
.col ul{list-style:none;margin:10px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px}.col li{margin:0;padding:3px 12px;border:1px solid var(--line);border-radius:999px;background:var(--bg);line-height:1.45;font-size:.9375rem}
.qa details{border-top:1px solid var(--line)}.qa summary{min-height:56px;font-size:1.0625rem}.qa p{margin:0 0 14px;line-height:1.6}
.link{margin:14px 0 0}.miss,.err{font-weight:600}.miss{color:var(--err)}
.say{margin-top:16px;background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:0 14px;color:var(--mute)}.say .plain li{margin:8px 0}
#nav{display:none}.js #nav{display:block;position:fixed;left:0;right:0;bottom:0;z-index:5;background:var(--bg);border-top:1px solid var(--line);padding:6px 12px calc(8px + env(safe-area-inset-bottom))}
#nav .in{max-width:900px;margin:0 auto}
.dots{display:flex;justify-content:center}.dots button{width:28px;min-height:32px;padding:0;border:0;background:none;display:flex;align-items:center;justify-content:center}
.dots button::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--bg);box-shadow:inset 0 0 0 1.5px var(--mute)}
.dots button[aria-current=true]::before{width:13px;height:13px;background:var(--acc);box-shadow:none}
.nv{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center}.nv button{min-height:52px;font-size:1.0625rem}
#nx{background:var(--acc);border-color:var(--acc);color:var(--on-acc);font-weight:600}#pos{min-width:64px;text-align:center;color:var(--mute);font-variant-numeric:tabular-nums}
button:disabled{opacity:.4;cursor:default}"""

JS = """<script>(function(){var d=document,b=d.body,S=[].slice.call(d.querySelectorAll('.slide')),D=[].slice.call(d.querySelectorAll('.dots button')),
i=0,$=function(x){return d.getElementById(x)},pv=$('pv'),nx=$('nx'),ps=$('pos'),x0=null,y0=0;b.classList.add('js');
function show(n,keep){i=Math.max(0,Math.min(S.length-1,n));S.forEach(function(s,k){s.classList.toggle('cur',k===i)});
D.forEach(function(e,k){e.setAttribute('aria-current',k===i)});ps.textContent=(i+1)+' / '+S.length;pv.disabled=i===0;nx.disabled=i===S.length-1;
if(!keep)window.scrollTo(0,0);try{history.replaceState(null,'','#'+(i+1))}catch(e){}}
pv.onclick=function(){show(i-1)};nx.onclick=function(){show(i+1)};D.forEach(function(e,k){e.onclick=function(){show(k)}});
d.addEventListener('keydown',function(e){if(e.altKey||e.ctrlKey||e.metaKey||/INPUT|TEXTAREA/.test((e.target||{}).tagName))return;
if(e.key==='ArrowRight')show(i+1);else if(e.key==='ArrowLeft')show(i-1);else if(e.key==='Home')show(0);else if(e.key==='End')show(S.length-1)});
d.addEventListener('touchstart',function(e){var t=e.touches[0];x0=t.clientX;y0=t.clientY},{passive:true});
d.addEventListener('touchend',function(e){if(x0===null)return;var t=e.changedTouches[0],dx=t.clientX-x0,dy=t.clientY-y0;x0=null;
if(Math.abs(dx)>60&&Math.abs(dx)>2*Math.abs(dy))show(i+(dx<0?1:-1))},{passive:true});
show((parseInt(location.hash.slice(1),10)||1)-1,true)})();</script>"""


def _speeches(say, d):
    """各頁講稿：沿用 about_page._speech 的口語稿，依頁挑句；None（缺資料）由 _say 略過。"""
    s3, s4 = say[3], say[4]
    r = retrieval
    hybrid = ([f"我原本以為{HYBRID}會更好。", _vs_line(d).rstrip("；"), "有差的題太少，不能說 bge-m3 真的比較好。", "結論是差異不大，沒必要加混合，所以用比較簡單的 bge-m3。"]
              if d and d["mrr_diff"]["lo"] <= 0 <= d["mrr_diff"]["hi"] else [None])
    return {
        "cover": say[1],
        "arch": ["資料進來，先切段、轉成向量、放進索引。", f"問題進來，先找最像的前 {r.DEFAULT_K} 段。",
                 f"最高相似度太低，就不呼叫 DeepSeek。", "答案附出處；評估另外離線跑一條迴路。"],
        "chunk": say[2],
        "methods": s3[:6] + [s3[7]],
        "forest": hybrid,
        "fixes": say[5],
        "funnel": s4[5:8],
        "cross": [s3[7], say[6][3] if len(say[6]) > 3 else None],
        "ragas": s4[0:5],
        "limits": say[6],
        "error": [], "qa": [],
    }


def render(data, error, n_segments, n_companies, lengths=None, companies=None) -> str:
    """data 為 None（輸出檔缺或過期）時，用不到評估輸出的頁照常顯示，評估圖表頁換成一頁錯誤說明。"""
    say = _speech(data, n_companies, n_segments)
    sp = _speeches(say, data)
    builders = [lambda: s_cover(data, n_segments, n_companies), lambda: s_arch(data, n_segments, n_companies), lambda: s_chunk(data, lengths)]
    if data:
        builders += [lambda: s_methods(data), lambda: s_held(data), lambda: s_score(data), lambda: s_qset(data), lambda: s_fixes(data), lambda: s_funnel(data, data.get("e2e")),
                     lambda: s_ragas(data), lambda: s_cross(data, n_companies, companies)]
    else:
        builders += [lambda: s_error(error)]
    builders += [lambda: s_limits(data), lambda: s_qa(data, n_segments)]
    slides = [b() for b in builders]
    slides = [s for s in slides if s]
    out, dots = [], []
    for i, (title, fig, notes, key, kick, *ex) in enumerate(slides, 1):
        k = f'<p class="kick">{escape(kick)}</p>' if kick else ""
        n = f'<div class="sn">{notes}</div>' if notes else ""
        sy = _say(sp[key]) if any(sp.get(key) or []) else ""
        out.append(f'<section class="slide" id="p{i}" data-slide="{key}" aria-label="第 {i} 頁">{k}<h2>{escape(title)}</h2><div class="fig">{fig}</div>{n}{ex[0] if ex else ""}{sy}</section>')
        dots.append(f'<button type="button" aria-label="第 {i} 頁：{escape(title)}"></button>')
    nav = ('<div id="nav"><div class="in"><div class="dots" role="group" aria-label="頁碼">' + "".join(dots) + '</div>'
           '<div class="nv"><button id="pv" type="button">‹ 上一頁</button><span id="pos" aria-live="polite"></span><button id="nx" type="button">下一頁 ›</button></div></div></div>')
    return page("專案說明｜求職情報問答", f'<header class="sh"><a href="/">← 問答</a><b>專案說明</b><a href="/about?all=1">全部展開</a></header>'
                f'<script>document.body.className="sl"</script><main>{"".join(out)}</main>{nav}{JS}', head=f"<style>{CSS}</style>")

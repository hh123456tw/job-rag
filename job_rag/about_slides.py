"""/about 的簡報版：一頁一句主張、一張主圖。圖是伺服器畫好的內嵌 SVG／HTML，不載外部函式庫；JS 只換頁。
數字全部來自 about.load() 的輸出與程式常數；缺資料的圖或頁直接略過（缺的是什麼寫在頁面上或回傳的錯誤裡），不用舊數字。
每個圖元素帶 data-v（原始數值），tests/test_about_slides.py 用它對照輸出檔。"""
import statistics

from markupsafe import escape

from . import METHODS, retrieval
from .about_page import GEN_NOTE, SHORT, _e2e, _f, _say, _speech, hist
from .ui import page

W = 340  # 圖的 viewBox 寬；手機約 1:1，桌面等比放大
INK = "sv"  # SVG 的樣式前綴（見 CSS）


def _t(x, y, s, cls="", anchor="start"):
    return f'<text x="{float(x):g}" y="{float(y):g}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>'


def _svg(h, label, body, defs=""):
    return (f'<svg class="{INK}" viewBox="0 0 {W} {h:g}" role="img" aria-label="{escape(label)}">{defs}{body}</svg>')


def _short(name, n=6):
    return name if len(name) <= n else name[: n - 1] + "…"


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
            ("索引", "FAISS", 0), (f"取前 K 段", f"K = {r.DEFAULT_K}", 0), ("查無門檻", f"低於 {r.NOT_FOUND_THRESHOLD:.3f} 就停", 0),
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
    ev = [("評估題", ""), ("MRR／Hit@k", ""), ("RAGAS", ""), ("GPT 複查", "")]
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
             f"<p>最高相似度低於 {r.NOT_FOUND_THRESHOLD:.3f}（已指定公司 {r.NOT_FOUND_THRESHOLD - r.SCOPED_DROP:.3f}）就不呼叫 DeepSeek。</p>")
    return f"一個問題，走過 {len(main)} 步", fig, notes, "arch", None


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
             f"<p>平均 {statistics.mean(lengths):.0f} 字、中位數 {statistics.median(lengths):.0f} 字、最長 {max(lengths)} 字。</p>")
    return f"{len(lengths)} 段，中位數 {statistics.median(lengths):.0f} 字", fig, notes, "chunk", None


def s_methods(d):
    rows = sorted(d["table"], key=lambda r: -r["mrr"])
    best = rows[0]
    # 圖 A：MRR 與 95% 區間
    lx, x0, x1, pitch, y0 = 0, 94, 292, 32, 8
    a = []
    for i, r in enumerate(rows):
        y = y0 + i * pitch
        lo, hi = r["ci"]["mrr"]
        sx = lambda v: x0 + v * (x1 - x0)
        hot = r["method"] == "bge-m3"
        a.append(_t(lx, y + 15, SHORT[r["method"]], "bd" if hot else "", "start")
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
        b.append(_t(lx, y + 17, SHORT[r["method"]], "bd" if hot else ""))
        for j, k in enumerate(("hit@1", "hit@3", "hit@5")):
            yy = y + j * (bh + 2)
            b.append(f'<rect class="bar gx h{k[-1]}" data-m="{r["method"]}" data-k="{k}" data-v="{r[k]!r}" x="{x0}" y="{yy}" width="{max(r[k] * (x1 - x0), 0.5):.1f}" height="{bh}" rx="2"/>'
                     + _t(x0 + r[k] * (x1 - x0) + 5, yy + 8, _f(r[k]), "xs"))
    yb = 20 + len(rows) * pitch2
    b.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>' + _ticks_h(x0, x1, yb, (0, .25, .5, .75, 1), lambda v: f"{v:g}")
             + _t(x0, yb + 34, "前 k 名內有正確段落的題數比例", "mu sm"))
    B = _svg(yb + 42, "各找法的 Hit@1、Hit@3、Hit@5", "".join(b))
    fig = f'<div class="two"><figure><figcaption>MRR（含 95% 區間）</figcaption>{A}</figure><figure><figcaption>Hit@1／3／5</figcaption>{B}</figure></div>'
    notes = (f"<p>用 {d['n_answerable']} 道有答案的題；MRR 是正確段落名次的倒數平均，區間重疊的差距只能當方向。</p>"
             f"<p>網站用 {retrieval.DEFAULT_METHOD}；問單一公司取前 {retrieval.DEFAULT_K} 段。</p>")
    head = f"{len(METHODS)} 種找法，{SHORT[best['method']]} 最高" if best["method"] == "bge-m3" else f"{len(METHODS)} 種找法比一比"
    return head, fig, notes, "methods", None


def _sgn(v):
    return f"{v:+.3f}".replace("-", "−")


def s_forest(d):
    rows = d["mrr_diffs"]
    lo = min(0, min(r["lo"] for r in rows)) - 0.04
    hi = max(r["hi"] for r in rows) + 0.04
    x0, x1, pitch, y0 = 10, W - 10, 52, 40
    X = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    n = len(rows)
    yb = y0 + n * pitch
    p = [_t(X(0) - 6, 12, "← 對方較好", "mu sm", "end"), _t(X(0) + 6, 12, "bge-m3 較好 →", "mu sm"),
         ]
    for i, r in enumerate(rows):
        y = y0 + i * pitch
        inc = r["lo"] <= 0 <= r["hi"]
        p.append(f'<line class="zero" x1="{X(0):.1f}" x2="{X(0):.1f}" y1="{y + 6}" y2="{y + 34}"/>' + _t(0, y, f"bge-m3 − {SHORT[r['method']]}", "bd halo")
                 + _t(W, y, f"{_sgn(r['diff'])}　[{_sgn(r['lo'])}, {_sgn(r['hi'])}]", "sm halo", "end")
                 + f'<g class="fr gx2"><line class="ci" x1="{X(r["lo"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{y + 20}" y2="{y + 20}"/>'
                 f'<line class="ci" x1="{X(r["lo"]):.1f}" x2="{X(r["lo"]):.1f}" y1="{y + 14}" y2="{y + 26}"/>'
                 f'<line class="ci" x1="{X(r["hi"]):.1f}" x2="{X(r["hi"]):.1f}" y1="{y + 14}" y2="{y + 26}"/>'
                 f'<circle class="pt{" open" if inc else ""}" data-m="{r["method"]}" data-v="{r["diff"]!r}" data-lo="{r["lo"]!r}" data-hi="{r["hi"]!r}" cx="{X(r["diff"]):.1f}" cy="{y + 20}" r="6"/></g>')
    ticks = [v / 10 for v in range(int(lo * 10) - 1, int(hi * 10) + 2) if lo <= v / 10 <= hi]
    p.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>'
             + "".join(f'<line class="ax" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{yb}" y2="{yb + 4}"/>' + _t(f"{X(v):.1f}", yb + 16, f"{v:g}", "mu sm", "middle") for v in ticks)
             + _t(W / 2, yb + 34, "MRR 的差（bge-m3 減對方），含 95% 區間", "mu sm", "middle")
             + f'<circle class="pt" cx="14" cy="{yb + 54}" r="5"/>' + _t(26, yb + 58, "區間不含 0：差距可信", "sm")
             + f'<circle class="pt open" cx="{W / 2 + 10}" cy="{yb + 54}" r="5"/>' + _t(W / 2 + 22, yb + 58, "區間含 0：看不出差距", "sm"))
    fig = _svg(yb + 66, "bge-m3 與其他找法的 MRR 差與 95% 區間（森林圖）", "".join(p))
    hy = next(r for r in rows if r["method"] == "hybrid")
    inc = hy["lo"] <= 0 <= hy["hi"]
    what = "<p><b>混合是什麼：</b>BM25（比對關鍵字）與 bge-m3（比對語意）各排一次名次，再用 RRF 把兩個名次合併：兩邊都排前面的段落分數最高。</p>"
    notes = (what + "<p>原本以為混合會贏；線碰到 0，代表這批題看不出差別，所以用較簡單的單一向量找法。</p>"
             if inc else what + "<p>混合與 bge-m3 的差距，區間不含 0，差異可信。</p>")
    return ("看不出混合比較好" if inc else "混合與 bge-m3 有差距"), fig, notes, "forest", None


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
    notes = "<p>檢索門檻單獨擋不乾淨，要靠答案層補上。</p><p>樣本小、同一人出題，只能當方向。</p>"
    return f"兩層把關：{e2e['refused']}/{n} 題拒答", f'<div class="two">{fig}{big}</div>{link}', notes, "funnel", None


def s_cross(d, n_companies, companies):
    x = d.get("cross_eval") if d else None
    per = retrieval.PER_COMPANY
    names = list(companies or [])[:n_companies] or [f"公司 {i + 1}" for i in range(n_companies)]
    cols, cw, ch, gap = 4, 76, 54, 12
    p = []
    for i, nm in enumerate(names):
        r, c = divmod(i, cols)
        sx, sy = c * (cw + gap) + (W - cols * cw - (cols - 1) * gap) / 2, r * (ch + gap)
        segs = "".join(f'<rect class="sg" x="{sx + 14 + k * 20:.1f}" y="{sy + 33}" width="16" height="9" rx="2"/>' for k in range(per))
        p.append(f'<rect class="co" x="{sx:.1f}" y="{sy}" width="{cw}" height="{ch}" rx="9"/>' + _t(sx + cw / 2, sy + 21, _short(nm), "bd sm", "middle") + segs)
    rows = (len(names) + cols - 1) // cols
    h = rows * (ch + gap)
    p.append(_t(W / 2, h + 14, f"每家各取 {per} 段（■）→ 合併 → 交給 DeepSeek 逐家整理", "mu sm", "middle"))
    schem = _svg(h + 24, f"跨公司示意：{len(names)} 家公司各取 {per} 段", "".join(p))
    fig = f'<div class="two"><figure><figcaption>問「全部公司」時</figcaption>{schem}</figure>'
    notes = ""
    if x and x["by_per"]:
        k_all = sorted(x["by_per"])
        pitch, x0, x1 = 34, 92, 290
        c = []
        for i, k in enumerate(k_all):
            v, y = x["by_per"][k], 4 + i * pitch
            hot = k == per
            c.append(_t(0, y + 16, f"每家取 {k} 段", "bd" if hot else "")
                     + f'<rect class="bar gx{"" if hot else " g"}" data-k="{k}" data-v="{v!r}" x="{x0}" y="{y}" width="{v * (x1 - x0):.1f}" height="22" rx="4"/>'
                     + _t(x0 + v * (x1 - x0) + 6, y + 16, _f(v), "bd sm"))
        yb = 4 + len(k_all) * pitch
        c.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>' + _ticks_h(x0, x1, yb, (0, .25, .5, .75, 1), lambda v: f"{v:g}")
                 + _t(x0, yb + 34, "涵蓋率（越高越好）", "mu sm"))
        cov = _svg(yb + 42, "每家取 1、2、3 段的涵蓋率", "".join(c))
        fig += f"<figure><figcaption>涵蓋率：每家取幾段</figcaption>{cov}</figure>"
        notes = (f"<p>涵蓋率：該出現的公司裡，取到正確段落的比例（{x['n_answerable']} 道有答案的題平均）。</p>"
                 f"<p>{x['n']} 題中 {x['passed']} 題結果正確；查無常數 {x['floor']} 用同批題挑，偏樂觀。</p>")
    else:
        fig += '<figure><p class="miss">缺資料：eval/results_cross.json 找不到或已過期，涵蓋率圖略過，只留示意圖。</p></figure>'
    fig += "</div>"
    return f"問全部公司：每家取 {per} 段", fig, notes, "cross", None


def s_ragas(d):
    g, c = d["generation"], d["cross"]
    if not g:
        return None
    x0, x1, pitch = 100, 290, 40
    bars = [("忠實度", g["faithfulness"], "faithfulness"), ("答案相關性", g["answer_relevancy"], "answer_relevancy")]
    p = []
    for i, (lab, v, k) in enumerate(bars):
        y = 4 + i * pitch
        p.append(_t(0, y + 17, lab, "bd") + f'<rect class="tk" x="{x0}" y="{y}" width="{x1 - x0}" height="24" rx="5"/>'
                 + f'<rect class="bar gx" data-k="{k}" data-v="{v!r}" x="{x0}" y="{y}" width="{v * (x1 - x0):.1f}" height="24" rx="5"/>'
                 + _t(x1 + 8, y + 17, _f(v), "bd"))
    yb = 4 + len(bars) * pitch
    p.append(f'<line class="ax" x1="{x0}" x2="{x1}" y1="{yb}" y2="{yb}"/>' + _ticks_h(x0, x1, yb, (0, .5, 1), lambda v: f"{v:g}")
             + _t(x0, yb + 34, f"RAGAS，{g['scored']} 題；滿分 1", "mu sm"))
    chart = _svg(yb + 42, "RAGAS 忠實度與答案相關性", "".join(p))
    chk = ""
    if c:
        chk = (f'<div class="e2e"><b data-v="{c["supported"]}" data-n="{c["claims"]}">{c["supported"]} / {c["claims"]}</b>'
               f'<span>個說法有依據（另請 GPT 獨立複查 {c["n"]} 題）</span>'
               f'<i class="tr"><i class="fl" style="width:{100 * c["supported"] / c["claims"]:.1f}%"></i></i></div>')
    notes = f"<p>評審與生成同為 DeepSeek，同模型自評可能偏樂觀，所以另請 GPT 複查。</p><p>{GEN_NOTE}</p>"
    return f"答案有依據：忠實度 {g['faithfulness']:.2f}", f'<div class="two">{chart}{chk}</div>', notes, "ragas", None


def _icon(path):
    return f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">{path}</svg>'


ICONS = {"warn": _icon('<path d="M12 3 2.5 20h19z"/><path d="M12 10v5M12 17.5v.5"/>'),
         "no": _icon('<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>'),
         "up": _icon('<path d="M5 19 19 5M9 5h10v10"/>')}


def s_limits(d):
    na, nu = (d["n_answerable"], d["n_unanswerable"]) if d else (None, None)
    lim = [f"題少：{na} 題有答案、{nu} 題沒答案" if d else "題少", "題目與語料同源" if not (d and d.get("held")) else "原題與語料同源；另有 40 題獨立測試題", "門檻用同批題挑，偏樂觀", "單機、單一存取碼"]
    undone = ["重排序模型", "向量資料庫", "微調模型", "線上監控"] + ([] if d and d.get("held") else ["獨立測試題"])
    nxt = ["近似索引，只編新段落", "PDF 與掃描檔解析", "改動後自動重考"]
    col = lambda ic, t, items, tag="": (f'<div class="col"><div class="ch">{ICONS[ic]}<h3>{escape(t)}</h3></div>{f"<em>{escape(tag)}</em>" if tag else ""}'
                                         + "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul></div>")
    fig = ('<div class="cols">' + col("warn", "限制", lim) + col("no", "沒做", undone)
           + col("up", "放大 100 倍，先做", nxt, "設計想法，尚未實作") + "</div>")
    return "限制、沒做的、下一步", fig, "", "limits", None


def s_qa(d, n_segments):
    m3 = next((r for r in d["table"] if r["method"] == "bge-m3"), None) if d else None
    df, gt = (d["mrr_diff"], d["gate"]) if d else (None, None)
    rows = [("資料放大 100 倍怎麼辦？", "沒做過；要換近似索引、只編新段落，再重新評估。"),
            ("為什麼不用重排序模型？", f"沒試過；bge-m3 的 MRR 已有 {_f(m3['mrr'])}，加了會不會更好沒量過。" if m3 else "沒試過，也沒量過。"),
            ("為什麼混合檢索沒有贏？",
             (f"bge-m3 減混合的 MRR 差 {df['diff']:+.3f}，區間 [{df['lo']:+.3f}, {df['hi']:+.3f}]"
              + ("，含 0，看不出混合比較好。" if df["lo"] <= 0 <= df["hi"] else "，不含 0。")) if df else "這份輸出沒有比較數字。"),
            ("查無門檻是不是太樂觀？",
             "是，門檻用同一批題挑。" + (f"沒有答案的題擋住 {gt['unanswerable_blocked']}/{gt['n_unanswerable']}{_e2e(d)}，有答案的題誤擋 {gt['answerable_blocked']}/{gt['n_answerable']}。" if gt else "")),
            ("沒有向量資料庫，算向量檢索嗎？", f"算；問題與 {n_segments} 段都轉成向量比相似度，用 FAISS 在記憶體內比。")]
    body = "".join(f"<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>" for q, a in rows)
    return "常被追問的 5 題", f'<div class="qa">{body}</div>', "<p>點一題，看一句話答案。</p>", "qa", None


def s_error(error):
    return "評估圖表無法顯示", f'<p class="err">無法顯示：{escape(error)}</p>', "<p>其餘頁面照常顯示；這裡不放舊數字。</p>", "error", None


# ---------- 組頁 ----------
CSS = """body.sl{max-width:900px;padding:0 16px 168px}
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
.sv .bar{fill:var(--acc)}.sv .bar.g{fill:var(--mute);fill-opacity:.55}
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
    hybrid = ["我原本以為混合會更好。", "這批題看不出差別，所以選比較簡單的 bge-m3。"] if d and d["mrr_diff"]["lo"] <= 0 <= d["mrr_diff"]["hi"] else [None]
    return {
        "cover": say[1],
        "arch": ["資料進來，先切段、轉成向量、放進索引。", f"問題進來，先找最像的前 {r.DEFAULT_K} 段。",
                 f"最高相似度太低，就不呼叫 DeepSeek。", "答案附出處；評估另外離線跑一條迴路。"],
        "chunk": say[2],
        "methods": s3[:6] + [s3[7]],
        "forest": hybrid + ["看線有沒有碰到 0：碰到，就是看不出差別。"],
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
        builders += [lambda: s_methods(data), lambda: s_forest(data), lambda: s_fixes(data), lambda: s_funnel(data, data.get("e2e")),
                     lambda: s_cross(data, n_companies, companies), lambda: s_ragas(data)]
    else:
        builders += [lambda: s_error(error)]
    builders += [lambda: s_limits(data), lambda: s_qa(data, n_segments)]
    slides = [b() for b in builders]
    slides = [s for s in slides if s]
    out, dots = [], []
    for i, (title, fig, notes, key, kick) in enumerate(slides, 1):
        k = f'<p class="kick">{escape(kick)}</p>' if kick else ""
        n = f'<div class="sn">{notes}</div>' if notes else ""
        sy = _say(sp[key]) if any(sp.get(key) or []) else ""
        out.append(f'<section class="slide" id="p{i}" data-slide="{key}" aria-label="第 {i} 頁">{k}<h2>{escape(title)}</h2><div class="fig">{fig}</div>{n}{sy}</section>')
        dots.append(f'<button type="button" aria-label="第 {i} 頁：{escape(title)}"></button>')
    nav = ('<div id="nav"><div class="in"><div class="dots" role="group" aria-label="頁碼">' + "".join(dots) + '</div>'
           '<div class="nv"><button id="pv" type="button">‹ 上一頁</button><span id="pos" aria-live="polite"></span><button id="nx" type="button">下一頁 ›</button></div></div></div>')
    return page("專案說明｜求職情報問答", f'<header class="sh"><a href="/">← 問答</a><b>專案說明</b><a href="/about?all=1">全部展開</a></header>'
                f'<script>document.body.className="sl"</script><main>{"".join(out)}</main>{nav}{JS}', head=f"<style>{CSS}</style>")

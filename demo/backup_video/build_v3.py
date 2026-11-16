"""第 3 版：由 plan_v3.py（分鏡與旁白）、hf3/assets/voice/durations.json（旁白長度）、錄影與簡報圖，
產生 hf3/assets/screen.mp4（手機畫面：錄影變速、簡報靜態圖，每景一段再接起來）與 hf3/index.html（時間線）。
用法：python -X utf8 build_v3.py <qa 錄影資料夾> <th 錄影資料夾>
      各資料夾需有 frames.txt（record_v3.py 產生）；簡報圖在 <qa 錄影資料夾>/slides/。raw.mp4 不存在時會由 frames.txt 產生。"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from plan_v3 import PLAN

HF = Path(__file__).parent / "hf3"
QA, TH = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
SRC = {"qa": QA, "th": TH}
dur = json.loads((HF / "assets/voice/durations.json").read_text(encoding="utf-8"))
LEAD, GAP = 0.25, 0.3
W, H = 700, 1515           # 手機螢幕（畫面像素）
S = W / 390                # CSS px -> 畫面 px
PX, PY = 190, 150          # 螢幕左上角
SW, SH = W * 2, H * 2      # screen.mp4 的解析度
BG = {"o": ("#fb923c", "#0b1220"), "b": ("#2563eb", "#ffffff")}

for k, d in SRC.items():   # 錄影影格 -> raw.mp4（30fps，維持 2.5 倍解析度）
    if not (d / "raw.mp4").exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(d / "frames.txt"), "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(d / "raw.mp4")], check=True)

# ---- 時間軸 ----
t = 0.0; sc = []
for i, p in enumerate(PLAN):
    strip = [re.sub(r"\[\[|\]\]", "", x[0] if isinstance(x, tuple) else x) for x in p["text"]]
    ds = [dur[f"{p['id']}_{n}"] for n in range(len(strip))]
    nxt_cut = i + 1 < len(PLAN) and PLAN[i + 1].get("cut")
    lead = 0.2 if p["id"] == "s0" else (0.18 if p.get("cut") else LEAD)
    tail = 0.1 if p["id"] == "s0" else (0.9 if p["id"] == "s9" else (0.12 if nxt_cut else 0.4))
    starts, a = [], t + lead
    for d in ds:
        starts.append(a); a += d + GAP
    D = lead + sum(ds) + GAP * (len(ds) - 1) + tail
    sc.append(dict(p=p, t=t, D=D, starts=starts, ds=ds)); t += D
END = t

def tm(s, x):  # 場景內秒數；L(句, 秒) -> 該句開始後幾秒
    return x if not isinstance(x, tuple) else s["starts"][x[1]] - s["t"] + x[2]

vid = [s for s in sc if s["p"]["src"]]
V0, V1 = vid[0]["t"], vid[-1]["t"] + vid[-1]["D"]
print({s["p"]["id"]: round(s["D"], 1) for s in sc}, "END", round(END, 1))

# ---- screen.mp4：每景一段 ----
seg = HF / "assets/_seg"; seg.mkdir(exist_ok=True)
for f in seg.glob("*.mp4"): f.unlink()
common = ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "30"]
speeds = {}
for s in vid:
    p = s["p"]; D = s["D"]; out = seg / f"{p['id']}.mp4"; kind = p["src"][0]
    if kind == "png":
        png = QA / "slides" / f"{p['src'][1]}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-t", f"{D:.3f}", "-i", str(png),
                        "-vf", f"scale={SW}:{SH}:flags=lanczos,format=yuv420p", *common, str(out)], check=True)
    else:
        _, key, a, b = p["src"]; L_ = b - a
        f = min(max(L_ / D, 0.4), 2.3); real = L_ / f; speeds[p["id"]] = round(f, 2)
        fc = (f"[0:v]trim={a}:{b},setpts=(PTS-STARTPTS)/{f:.4f},fps=30,scale={SW}:{SH}:flags=lanczos,"
              f"tpad=stop_mode=clone:stop_duration={max(D - real, 0) + 0.2:.3f},trim=duration={D:.3f},setpts=PTS-STARTPTS[o]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(SRC[key] / "raw.mp4"), "-filter_complex", fc, "-map", "[o]", *common, str(out)], check=True)
(seg / "list.txt").write_text("\n".join(f"file '{s['p']['id']}.mp4'" for s in vid), encoding="utf-8")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(seg / "list.txt"), "-c", "copy", str(HF / "assets/screen.mp4")], check=True)
print("speeds", speeds)

# ---- HTML ----
aud = cap = rings = tags = chips = panels = ""
js = []
cams = []
k = 0
chap = []  # (章節標籤, 起, 迄)
for s in sc:
    p = s["p"]; T = s["t"]; i = p["id"]
    for n, (txt, st, d) in enumerate(zip(p["text"], s["starts"], s["ds"])):
        aud += f'<audio id="a_{i}_{n}" src="assets/voice/{i}_{n}.mp3" data-start="{st:.3f}" data-duration="{d:.3f}" data-track-index="3" data-volume="1.55"></audio>\n'
        k += 1
        c = txt[0] if isinstance(txt, tuple) else txt
        html = re.sub(r"\[\[(.+?)\]\]", r'<em class="k"><i></i>\1</em>', c)
        end = st + d + 0.12
        cap += f'<div id="c{k}" class="clip cap" data-start="{st - 0.05:.3f}" data-duration="{end - st + 0.05:.3f}" data-track-index="5"><span class="txt">{html}</span></div>\n'
        js.append(f'tl.fromTo("#c{k} .txt",{{clipPath:"inset(0 100% 0 0)",y:14}},{{clipPath:"inset(0 0% 0 0)",y:0,duration:0.32,ease:"power3.out"}},{st - 0.05:.3f});')
        if "<em" in html:
            js.append(f'tl.fromTo("#c{k} .k i",{{scaleX:0}},{{scaleX:1,duration:0.28,ease:"power2.out"}},{st + 0.3:.3f});')
        js.append(f'tl.to("#c{k}",{{opacity:0,duration:0.12}},{end - 0.12:.3f});')
    if not p["src"]:
        continue
    if p.get("step"): chap.append([p["step"], T, T + s["D"]])
    else: chap[-1][2] = T + s["D"]
    # 運鏡：x,y 夾在 [W-W*k, 0]；先收集，最後統一排序，讓前一段運鏡在下一個鏡頭開始前結束
    for e in p["cam"]:
        if len(e) == 3:  # (時間, (x0,y0,x1,y1), 運鏡秒數)：框住要看的東西，倍率由框的寬度算（寬 +24 內放得下，1.0~2.5 倍）
            o, (bx0, by0, bx1, by1), dd = e
            cx, cy, kk = (bx0 + bx1) / 2, (by0 + by1) / 2, round(max(1.0, min(2.5, 390 / (bx1 - bx0 + 24), 844 / (by1 - by0 + 24))), 2)
        else: o, cx, cy, kk, dd = e
        o = tm(s, o)
        cams.append((T + o, min(0, max(W - W * kk, W / 2 - cx * S * kk)), min(0, max(H - H * kk, H / 2 - cy * S * kk)), kk, dd))
    for j, (a, b, cx, cy, rx, ry) in enumerate(p["ring"]):
        a, b = tm(s, a), min(tm(s, b), s["D"] - 0.05)
        w, h = 2 * rx * S, 2 * ry * S; rid = f"ring_{i}_{j}"
        rings += (f'<div id="{rid}" class="clip ring" data-start="{T + a:.3f}" data-duration="{b - a:.3f}" data-track-index="4" '
                  f'style="left:{(cx - rx) * S:.0f}px;top:{(cy - ry) * S:.0f}px;width:{w:.0f}px;height:{h:.0f}px">'
                  f'<svg viewBox="0 0 {w:.0f} {h:.0f}"><ellipse pathLength="1" cx="{w / 2:.0f}" cy="{h / 2:.0f}" rx="{w / 2 - 6:.0f}" ry="{h / 2 - 6:.0f}"/></svg></div>\n')
        js.append(f'tl.fromTo("#{rid} ellipse",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:0.55,ease:"power2.inOut"}},{T + a:.3f});')
        js.append(f'tl.to("#{rid}",{{opacity:0,duration:0.25}},{T + b - 0.25:.3f});')
    for j, (a, b, text, x, y, c) in enumerate(p["tag"]):
        a, b = tm(s, a), min(tm(s, b), s["D"] - 0.05)
        tid = f"tag_{i}_{j}"; bg, fg = BG[c]
        tags += f'<div id="{tid}" class="clip tag" data-start="{T + a:.3f}" data-duration="{b - a:.3f}" data-track-index="6" style="left:{x}px;top:{y}px;background:{bg};color:{fg}">{text}</div>\n'
        js.append(f'tl.set("#{tid}",{{xPercent:-50,yPercent:-50}},0);')
        js.append(f'tl.fromTo("#{tid}",{{scale:0.5,opacity:0}},{{scale:1,opacity:1,duration:0.4,ease:"back.out(1.7)"}},{T + a:.3f});')
        js.append(f'tl.to("#{tid}",{{opacity:0,scale:0.9,duration:0.2}},{T + b - 0.2:.3f});')

cams.sort()
for n, (ct, x, y, kk, dd) in enumerate(cams):
    gap = (cams[n + 1][0] - ct - 0.02) if n + 1 < len(cams) else dd
    dd = min(dd, gap)
    if dd < 0.05: js.append(f'tl.set("#zoom",{{x:{x:.1f},y:{y:.1f},scale:{kk}}},{ct:.3f});')
    else: js.append(f'tl.to("#zoom",{{x:{x:.1f},y:{y:.1f},scale:{kk},duration:{dd:.2f},ease:"power3.inOut"}},{ct:.3f});')
# 章節標籤（頂部）與轉場蓋板（章節換景時，藍色板從右／下掃過，板中央就是剪接點）
for n, (name, a, b) in enumerate(chap):
    num, lab = name[:2], name[3:]
    chips += f'<div id="chip{n}" class="clip chip" data-start="{a:.3f}" data-duration="{b - a:.3f}" data-track-index="2"><b>{num}</b>{lab}</div>\n'
    js.append(f'tl.fromTo("#chip{n}",{{y:-30,opacity:0}},{{y:0,opacity:1,duration:0.4,ease:"power3.out"}},{a + 0.3:.3f});')
    js.append(f'tl.to("#chip{n}",{{opacity:0,duration:0.15}},{b - 0.2:.3f});')
    if n > 0:
        vert = n % 2 == 0
        panels += f'<div id="pn{n}" class="clip panel" data-start="{a - 0.32:.3f}" data-duration="0.7" data-track-index="7"><b>{num}</b><span>{lab}</span></div>\n'
        ax = "yPercent" if vert else "xPercent"
        js.append(f'tl.fromTo("#pn{n}",{{{ax}:100}},{{{ax}:0,duration:0.26,ease:"power3.in"}},{a - 0.28:.3f});')
        js.append(f'tl.to("#pn{n}",{{{ax}:-100,duration:0.3,ease:"power3.out"}},{a + 0.02:.3f});')

TS = sc[0]["D"]; OUT = sc[-1]["t"]
js.append('tl.fromTo("#title .ch",{y:70,opacity:0.2},{y:0,opacity:1,duration:0.45,stagger:0.05,ease:"expo.out"},0);')
js.append('tl.fromTo("#title .sub",{opacity:0,y:20},{opacity:1,y:0,duration:0.5,ease:"power3.out"},0.45);')
js.append('tl.fromTo("#title .pills span",{opacity:0,y:16},{opacity:1,y:0,duration:0.4,stagger:0.12,ease:"power3.out"},0.8);')
js.append(f'tl.to("#title",{{yPercent:-100,duration:0.5,ease:"power3.inOut"}},{TS - 0.5:.3f});')
js.append(f'tl.fromTo("#outro",{{yPercent:100}},{{yPercent:0,duration:0.45,ease:"power3.out"}},{OUT:.3f});')
js.append(f'tl.fromTo("#outro .ln",{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.5,stagger:0.5,ease:"power3.out"}},{OUT + 0.5:.3f});')
js.append(f'tl.fromTo("#outro .small",{{opacity:0}},{{opacity:1,duration:0.6}},{OUT + 2.2:.3f});')
js.append(f'tl.fromTo("#prog",{{scaleX:0}},{{scaleX:1,duration:{END - TS:.2f},ease:"none"}},{TS:.2f});')
js.append(f'tl.fromTo("#bg",{{"--x1":"18%","--y1":"22%","--x2":"80%","--y2":"60%"}},{{"--x1":"60%","--y1":"40%","--x2":"30%","--y2":"78%",duration:{END:.2f},ease:"sine.inOut"}},0);')

html = f'''<!doctype html>
<html lang="zh-Hant" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face {{ font-family:"NotoTC"; src:url("assets/fonts/NotoSansTC-VF.ttf"); font-weight:100 900; }}
:root {{ --ground:#0b1220; --brand:#2563eb; --ink:#f8fafc; --accent:#fb923c; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:1080px; height:1920px; overflow:hidden; background:var(--ground); }}
#root {{ position:relative; width:1080px; height:1920px; overflow:hidden; font-family:"NotoTC",sans-serif; color:var(--ink); background:var(--ground); }}
#bg {{ position:absolute; inset:0; --x1:18%; --y1:22%; --x2:80%; --y2:60%;
  background: radial-gradient(circle at var(--x1) var(--y1), rgba(37,99,235,.55) 0, transparent 38%), radial-gradient(circle at var(--x2) var(--y2), rgba(251,146,60,.28) 0, transparent 34%), var(--ground); }}
#bezel {{ position:absolute; left:{PX - 14}px; top:{PY - 14}px; width:{W + 28}px; height:{H + 28}px; border-radius:60px; background:#020617; box-shadow:0 30px 90px rgba(0,0,0,.55), 0 0 0 3px #1e3a8a; }}
#phone {{ position:absolute; left:{PX}px; top:{PY}px; width:{W}px; height:{H}px; border-radius:46px; overflow:hidden; background:#fafaf9; }}
#zoom {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; transform-origin:0 0; }}
#screen {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; display:block; }}
.ring {{ position:absolute; pointer-events:none; }}
.ring svg {{ width:100%; height:100%; overflow:visible; }}
.ring ellipse {{ fill:none; stroke:#fb923c; stroke-width:6; stroke-linecap:round; stroke-dasharray:1; stroke-dashoffset:1; transform:rotate(-4deg); transform-origin:50% 50%; }}
.tag {{ position:absolute; padding:16px 38px; border-radius:999px; font-size:52px; font-weight:900; white-space:nowrap; box-shadow:0 14px 40px rgba(0,0,0,.45); z-index:30; }}
.chip {{ position:absolute; left:0; right:0; top:50px; text-align:center; font-size:44px; font-weight:800; z-index:35; }}
.chip b {{ display:inline-block; margin-right:16px; padding:2px 18px; border-radius:14px; background:var(--brand); font-weight:900; }}
.panel {{ position:absolute; inset:0; background:linear-gradient(135deg,#1d4ed8,#2563eb 60%,#3b82f6); display:flex; align-items:center; justify-content:center; gap:36px; z-index:40; }}
.panel b {{ font-size:240px; font-weight:900; line-height:1; }}
.panel span {{ font-size:84px; font-weight:900; }}
.cap {{ position:absolute; left:90px; right:90px; top:1700px; height:190px; display:flex; align-items:center; justify-content:center; text-align:center; font-size:54px; line-height:1.36; font-weight:800; z-index:70; text-wrap:balance; text-shadow:0 4px 18px rgba(0,0,0,.6); }}
.cap .k {{ position:relative; font-style:normal; color:#fff; display:inline-block; padding:0 6px; }}
.cap .k i {{ position:absolute; inset:2px -2px; background:var(--brand); border-radius:12px; z-index:-1; transform-origin:0 50%; }}
#prog {{ position:absolute; left:0; top:0; width:1080px; height:8px; background:var(--accent); transform-origin:0 50%; z-index:80; }}
#title {{ position:absolute; inset:0; z-index:60; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:0 80px;
  background: radial-gradient(circle at 20% 15%, #2563eb 0, transparent 45%), radial-gradient(circle at 85% 85%, rgba(251,146,60,.5) 0, transparent 40%), #0b1220; }}
#title h1 {{ font-size:150px; font-weight:900; line-height:1.1; letter-spacing:.02em; display:flex; }}
#title .ch {{ display:inline-block; }}
#title .sub {{ margin-top:56px; font-size:64px; font-weight:800; color:var(--accent); line-height:1.4; }}
#title .pills {{ margin-top:90px; display:flex; gap:18px; justify-content:center; flex-wrap:wrap; }}
#title .pills span {{ padding:12px 30px; border:3px solid rgba(248,250,252,.5); border-radius:999px; font-size:38px; font-weight:700; }}
#outro {{ position:absolute; inset:0; z-index:60; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:46px;
  background: radial-gradient(circle at 80% 10%, #1d4ed8 0, transparent 45%), #0b1220; padding:0 110px; }}
#outro .ln {{ font-size:50px; font-weight:800; text-align:center; line-height:1.4; }}
#outro .ln b {{ color:var(--accent); font-weight:900; }}
#outro .small {{ margin-top:50px; font-size:32px; font-weight:700; text-align:center; color:rgba(248,250,252,.7); letter-spacing:.3em; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{END:.2f}" data-width="1080" data-height="1920">
<div id="bg"></div>
<div id="bezel"></div>
<div id="phone"><div id="zoom">
<video id="screen" class="clip" src="assets/screen.mp4" muted playsinline data-start="{V0:.3f}" data-duration="{V1 - V0:.3f}" data-track-index="1"></video>
{rings}</div></div>
{chips}{tags}{panels}{aud}{cap}
<div id="prog" class="clip" data-start="0" data-duration="{END:.2f}" data-track-index="10"></div>
<div id="title" class="clip" data-start="0" data-duration="{TS:.3f}" data-track-index="9"><h1>{"".join(f'<span class="ch">{c}</span>' for c in "求職情報問答")}</h1><div class="sub">RAG 怎麼選、怎麼驗、怎麼擋</div><div class="pills"><span>檢索比較</span><span>兩層把關</span><span>誠實評估</span></div></div>
<div id="outro" class="clip" data-start="{OUT:.3f}" data-duration="{END - OUT:.3f}" data-track-index="9"><div class="ln">資料都是<b>公開</b>的</div><div class="ln">評估題目少，<b>只能當方向</b></div><div class="ln">另有 <b>40 題</b>獨立測試題</div><div class="small">示範錄影</div></div>
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
window.__timelines["main"] = tl;
</script>
</body></html>'''
(HF / "index.html").write_text(html, encoding="utf-8")
print("ok", round(END, 1))

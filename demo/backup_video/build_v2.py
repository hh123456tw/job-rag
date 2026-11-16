"""第 2 版：由 plan_v2.py（分鏡）、lines_v2.json（旁白）、hf2/assets/voice/durations.json（旁白長度）
產生 hf2/assets/screen.mp4（錄影依旁白長度變速、補停格）與 hf2/index.html（時間線）。
用法：python -X utf8 build_v2.py <raw.webm>"""
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from plan_v2 import PLAN

HF = Path(__file__).parent / "hf2"
raw = sys.argv[1]
dur = json.loads((HF / "assets/voice/durations.json").read_text(encoding="utf-8"))
lines = json.loads((Path(__file__).parent / "lines_v2.json").read_text(encoding="utf-8"))["scenes"]
LEAD, GAP, TAIL = 0.25, 0.22, 0.35
W, H = 580, 1255           # 手機螢幕（畫面像素）
S = W / 390                # 錄影 CSS px -> 畫面 px
PX, PY = 250, 305          # 螢幕左上角
BG = {"o": ("#fb923c", "#0b1220"), "b": ("#2563eb", "#ffffff")}

t = 0.0; sc = []
for p in PLAN:
    strip = [re.sub(r"\[\[|\]\]", "", x) for x in p["text"]]
    assert strip == lines[p["id"]], (p["id"], strip)
    ds = [dur[f"{p['id']}_{i}"] for i in range(len(strip))]
    lead = 0.2 if p["id"] == "s0" else LEAD
    tail = 0.1 if p["id"] == "s0" else (0.8 if p["id"] == "s9" else TAIL)
    starts, a = [], t + lead
    for d in ds:
        starts.append(a); a += d + GAP
    D = lead + sum(ds) + GAP * (len(ds) - 1) + tail
    sc.append(dict(p=p, t=t, D=D, starts=starts, ds=ds)); t += D
END = t
vid = [s for s in sc if s["p"]["raw"]]
V0, V1 = vid[0]["t"], vid[-1]["t"] + vid[-1]["D"]
print({s["p"]["id"]: round(s["D"], 2) for s in sc}, "END", round(END, 2))

# ---- screen.mp4：每場景一段，變速到旁白長度（上限 0.5x~2.3x），不夠補最後一格，太長截掉 ----
fc = []
for i, s in enumerate(vid):
    a, b = s["p"]["raw"]; L = b - a; D = s["D"]
    f = min(max(L / D, 0.5), 2.3); real = L / f
    s["speed"] = round(f, 2)
    fc.append(f"[0:v]trim={a}:{b},setpts=(PTS-STARTPTS)/{f:.4f},fps=30,scale={W * 2}:{H * 2}:flags=lanczos,"
              f"tpad=stop_mode=clone:stop_duration={max(D - real, 0) + 0.2:.3f},trim=duration={D:.3f},setpts=PTS-STARTPTS[v{i}]")
fc.append("".join(f"[v{i}]" for i in range(len(vid))) + f"concat=n={len(vid)}:v=1:a=0[o]")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-filter_complex", ";".join(fc), "-map", "[o]", "-c:v", "libx264",
                "-crf", "17", "-pix_fmt", "yuv420p", str(HF / "assets/screen.mp4")], check=True)
print("speeds", {s["p"]["id"]: s["speed"] for s in vid})

# ---- HTML ----
aud = cap = rings = tags = steps = panels = ""
js = []
k = 0
for s in sc:
    p = s["p"]; i = p["id"]
    for n, (txt, st, d) in enumerate(zip(p["text"], s["starts"], s["ds"])):
        aud += f'<audio id="a_{i}_{n}" src="assets/voice/{i}_{n}.mp3" data-start="{st:.3f}" data-duration="{d:.3f}" data-track-index="3"></audio>\n'
        k += 1
        html = re.sub(r"\[\[(.+?)\]\]", r'<em class="k"><i></i>\1</em>', txt)
        end = st + d + 0.12
        cap += f'<div id="c{k}" class="clip cap" data-start="{st - 0.05:.3f}" data-duration="{end - st + 0.05:.3f}" data-track-index="5"><span class="txt">{html}</span></div>\n'
        js.append(f'tl.fromTo("#c{k} .txt",{{clipPath:"inset(0 100% 0 0)",y:14}},{{clipPath:"inset(0 0% 0 0)",y:0,duration:0.32,ease:"power3.out"}},{st - 0.05:.3f});')
        if "<em" in html:
            js.append(f'tl.fromTo("#c{k} .k i",{{scaleX:0}},{{scaleX:1,duration:0.28,ease:"power2.out"}},{st + 0.3:.3f});')
        js.append(f'tl.to("#c{k}",{{opacity:0,duration:0.12}},{end - 0.12:.3f});')
    if not p["raw"]:
        continue
    T = s["t"]
    steps += f'<div id="step_{i}" class="clip step" data-start="{T:.3f}" data-duration="{s["D"]:.3f}" data-track-index="2"><b>{p["step"][:2]}</b>{p["step"][3:]}</div>\n'
    js.append(f'tl.fromTo("#step_{i}",{{y:-26,opacity:0}},{{y:0,opacity:1,duration:0.35,ease:"power3.out"}},{T + 0.3:.3f});')
    js.append(f'tl.to("#step_{i}",{{opacity:0,duration:0.15}},{T + s["D"] - 0.2:.3f});')
    # 運鏡：x,y 夾在 [W-W*k, 0]
    for j, (o, cx, cy, kk, dd) in enumerate(p["cam"]):
        x = min(0, max(W - W * kk, W / 2 - cx * S * kk)); y = min(0, max(H - H * kk, H / 2 - cy * S * kk))
        if dd == 0:
            js.append(f'tl.set("#zoom",{{x:{x:.1f},y:{y:.1f},scale:{kk}}},{T + o:.3f});')
        else:
            js.append(f'tl.to("#zoom",{{x:{x:.1f},y:{y:.1f},scale:{kk},duration:{dd},ease:"power3.inOut"}},{T + o:.3f});')
    for j, (a, b, cx, cy, rx, ry) in enumerate(p["ring"]):
        w, h = 2 * rx * S, 2 * ry * S; rid = f"ring_{i}_{j}"
        rings += (f'<div id="{rid}" class="clip ring" data-start="{T + a:.3f}" data-duration="{b - a:.3f}" data-track-index="4" '
                  f'style="left:{(cx - rx) * S:.0f}px;top:{(cy - ry) * S:.0f}px;width:{w:.0f}px;height:{h:.0f}px">'
                  f'<svg viewBox="0 0 {w:.0f} {h:.0f}"><ellipse pathLength="1" cx="{w / 2:.0f}" cy="{h / 2:.0f}" rx="{w / 2 - 6:.0f}" ry="{h / 2 - 6:.0f}"/></svg></div>\n')
        js.append(f'tl.fromTo("#{rid} ellipse",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:0.55,ease:"power2.inOut"}},{T + a:.3f});')
        js.append(f'tl.to("#{rid}",{{opacity:0,duration:0.25}},{T + b - 0.25:.3f});')
    for j, (a, b, text, x, y, c) in enumerate(p["tag"]):
        tid = f"tag_{i}_{j}"; bg, fg = BG[c]
        tags += f'<div id="{tid}" class="clip tag" data-start="{T + a:.3f}" data-duration="{b - a:.3f}" data-track-index="6" style="left:{x}px;top:{y}px;background:{bg};color:{fg}">{text}</div>\n'
        js.append(f'tl.set("#{tid}",{{xPercent:-50,yPercent:-50}},0);')
        js.append(f'tl.fromTo("#{tid}",{{scale:0.5,opacity:0}},{{scale:1,opacity:1,duration:0.4,ease:"back.out(1.7)"}},{T + a:.3f});')
        js.append(f'tl.to("#{tid}",{{opacity:0,scale:0.9,duration:0.2}},{T + b - 0.2:.3f});')

# 轉場：蓋板從右（h）或從下（v）掃過，板中央剛好是錄影的硬切點；板上是下一場景的步驟編號
seams = [(s["t"], s["p"]) for s in vid[1:]] + [(END - sc[-1]["D"], None)]
for n, (T, p) in enumerate(seams):
    label = (f'<b>{p["step"][:2]}</b><span>{p["step"][3:]}</span>' if p else '<b>!</b><span>誠實聲明</span>')
    vert = n % 2 == 1
    panels += f'<div id="pn{n}" class="clip panel" data-start="{T - 0.32:.3f}" data-duration="0.7" data-track-index="7">{label}</div>\n'
    ax = "yPercent" if vert else "xPercent"
    js.append(f'tl.fromTo("#pn{n}",{{{ax}:100}},{{{ax}:0,duration:0.26,ease:"power3.in"}},{T - 0.28:.3f});')
    js.append(f'tl.to("#pn{n}",{{{ax}:-100,duration:0.3,ease:"power3.out"}},{T + 0.02:.3f});')

TS = sc[0]["D"]  # 片頭結束
OUT = sc[-1]["t"]
js.append(f'tl.fromTo("#title .ch",{{y:60,opacity:0.2}},{{y:0,opacity:1,duration:0.45,stagger:0.05,ease:"expo.out"}},0);')
js.append('tl.fromTo("#title .sub",{opacity:0,y:20},{opacity:1,y:0,duration:0.5,ease:"power3.out"},0.45);')
js.append('tl.fromTo("#title .pill",{opacity:0},{opacity:1,duration:0.4},0.8);')
js.append(f'tl.to("#title",{{yPercent:-100,duration:0.5,ease:"power3.inOut"}},{TS - 0.5:.3f});')
js.append(f'tl.fromTo("#outro",{{yPercent:100}},{{yPercent:0,duration:0.45,ease:"power3.out"}},{OUT:.3f});')
js.append(f'tl.fromTo("#outro li",{{opacity:0,x:40}},{{opacity:1,x:0,duration:0.4,stagger:0.45,ease:"power3.out"}},{OUT + 0.5:.3f});')
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
#bezel {{ position:absolute; left:{PX - 14}px; top:{PY - 14}px; width:{W + 28}px; height:{H + 28}px; border-radius:64px; background:#020617; box-shadow:0 30px 90px rgba(0,0,0,.55), 0 0 0 3px #1e3a8a; }}
#phone {{ position:absolute; left:{PX}px; top:{PY}px; width:{W}px; height:{H}px; border-radius:48px; overflow:hidden; background:#fafaf9; }}
#zoom {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; transform-origin:0 0; }}
#screen {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; display:block; }}
.ring {{ position:absolute; pointer-events:none; }}
.ring svg {{ width:100%; height:100%; overflow:visible; }}
.ring ellipse {{ fill:none; stroke:#fb923c; stroke-width:7; stroke-linecap:round; stroke-dasharray:1; stroke-dashoffset:1; transform:rotate(-4deg); transform-origin:50% 50%; }}
.tag {{ position:absolute; padding:16px 38px; border-radius:999px; font-size:56px; font-weight:900; white-space:nowrap; box-shadow:0 14px 40px rgba(0,0,0,.45); z-index:30; }}
.step {{ position:absolute; left:0; right:0; top:176px; text-align:center; font-size:40px; font-weight:700; z-index:35; }}
.step b {{ display:inline-block; margin-right:16px; padding:2px 16px; border-radius:14px; background:var(--brand); font-weight:900; }}
.badge {{ position:absolute; left:0; right:0; top:240px; text-align:center; font-size:28px; font-weight:700; color:var(--accent); z-index:36; letter-spacing:.06em; }}
.panel {{ position:absolute; inset:0; background:linear-gradient(135deg,#1d4ed8,#2563eb 60%,#3b82f6); display:flex; align-items:center; justify-content:center; gap:36px; z-index:40; }}
.panel b {{ font-size:260px; font-weight:900; line-height:1; }}
.panel span {{ font-size:84px; font-weight:900; }}
.cap {{ position:absolute; left:100px; right:100px; top:1640px; height:200px; display:flex; align-items:center; justify-content:center; text-align:center; font-size:58px; line-height:1.38; font-weight:800; z-index:70; text-wrap:balance; text-shadow:0 4px 18px rgba(0,0,0,.6); }}
.cap .k {{ position:relative; font-style:normal; color:#fff; display:inline-block; padding:0 6px; }}
.cap .k i {{ position:absolute; inset:2px -2px; background:var(--brand); border-radius:12px; z-index:-1; transform-origin:0 50%; }}
#title {{ position:absolute; inset:0; z-index:60; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:0 80px;
  background: radial-gradient(circle at 20% 15%, #2563eb 0, transparent 45%), radial-gradient(circle at 85% 85%, rgba(251,146,60,.5) 0, transparent 40%), #0b1220; }}
#title h1 {{ font-size:150px; font-weight:900; line-height:1.1; letter-spacing:.02em; display:flex; }}
#title .ch {{ display:inline-block; }}
#title .sub {{ margin-top:56px; font-size:66px; font-weight:800; color:var(--accent); line-height:1.4; }}
#title .pill {{ margin-top:90px; padding:14px 38px; border:3px solid rgba(248,250,252,.5); border-radius:999px; font-size:36px; font-weight:700; }}
#outro {{ position:absolute; inset:0; z-index:60; display:flex; flex-direction:column; justify-content:flex-start; padding:520px 150px 0 100px;
  background: radial-gradient(circle at 80% 10%, #1d4ed8 0, transparent 45%), #0b1220; }}
#outro h2 {{ font-size:96px; font-weight:900; margin-bottom:50px; }}
#outro ul {{ list-style:none; }}
#outro li {{ font-size:54px; font-weight:700; line-height:1.5; margin-bottom:40px; padding-left:56px; position:relative; }}
#outro li::before {{ content:""; position:absolute; left:0; top:28px; width:26px; height:26px; border-radius:8px; background:var(--accent); }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{END:.2f}" data-width="1080" data-height="1920">
<div id="bg"></div>
<div id="bezel"></div>
<div id="phone"><div id="zoom">
<video id="screen" class="clip" src="assets/screen.mp4" muted playsinline data-start="{V0:.3f}" data-duration="{V1 - V0:.3f}" data-track-index="1"></video>
{rings}</div></div>
<div id="badge" class="clip badge" data-start="{V0:.3f}" data-duration="{V1 - V0:.3f}" data-track-index="8">示範錄影・電腦螢幕錄製・非真機</div>
{steps}{tags}{panels}{aud}{cap}
<div id="title" class="clip" data-start="0" data-duration="{TS:.3f}" data-track-index="9"><h1>{"".join(f'<span class="ch">{c}</span>' for c in "求職情報問答")}</h1><div class="sub">問一家公司，<br/>答案附出處</div><div class="pill">示範錄影・電腦螢幕錄製・非真機</div></div>
<div id="outro" class="clip" data-start="{OUT:.3f}" data-duration="{END - OUT:.3f}" data-track-index="9"><h2>誠實聲明</h2><ul>
<li>資料來源是公開的求職資料，共 13 家公司、344 段。</li>
<li>畫面是電腦 Chrome 手機尺寸的螢幕錄製，不是真手機；配音是電腦合成語音。</li>
<li>評估題目少，和語料同源，只能當方向。</li></ul></div>
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

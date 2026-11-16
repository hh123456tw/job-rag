"""由旁白長度與場景長度產生 hf/index.html（字幕、配音、畫面的時間線）。
用法：python -X utf8 demo/backup_video/gen_index.py   （先有 hf/assets/screen.mp4 與 hf/assets/voice/n1..n7.wav）"""
import json
from pathlib import Path

HF = Path(__file__).parent / "hf"
D = [7.1, 7.61, 9.65, 9.2, 6.12, 11.2, 10.5]  # 每場景秒數 = max(旁白長度+0.5, 錄影片段長度)
nar = [6.597, 7.106, 9.150, 8.345, 5.622, 8.182, 10.010]  # 各旁白 wav 長度
S = [sum(D[:i]) for i in range(7)]
T0 = 3.0
SCR = sum(D)
OUT = T0 + SCR
END = OUT + 4
# 字幕時間：由 ffmpeg silencedetect 量到的各句起迄（相對旁白開頭）
cues = [
    [("這是我做的求職資料問答。", 0, 3.34), ("點一家公司，就能問問題。", 3.39, 6.2)],
    [("進到叡揚資訊。", 0, 2.36), ("畫面先說這家有哪些資料，沒有哪些資料。", 2.41, 6.7)],
    [("我輸入：薪水多少。", 0, 2.74), ("系統先搜尋，再整理答案。", 2.79, 6.16), ("這一步真的呼叫了 DeepSeek。", 6.21, 8.7)],
    [("答案列出各職缺的薪資範圍。", 0, 3.7), ("點一號來源，就看到原文和相似度分數。", 3.76, 7.95)],
    [("回到首頁，再問跨公司的題目：哪些公司用 Python。", 0, 5.25)],
    [("系統每家公司各找兩段，逐家回答。", 0, 4.4), ("資料沒寫的，就直接說資料沒寫。", 4.45, 7.75)],
    [("最後是專案說明頁。", 0, 2.67), ("我用簡報模式翻頁。", 2.72, 5.3), ("評估題目和語料同源，數字只能當方向。", 5.36, 9.55)],
]
aud = cap = tw = ""
k = 0
for i in range(7):
    a0 = T0 + S[i] + 0.2
    aud += f'<audio id="n{i+1}" src="assets/voice/n{i+1}.wav" data-start="{a0:.2f}" data-duration="{nar[i]:.2f}" data-track-index="3"></audio>\n'
    for t, s, e in cues[i]:
        k += 1
        st = a0 + s
        cap += f'<div id="c{k}" class="clip cap" data-start="{st:.2f}" data-duration="{e - s:.2f}" data-track-index="5"><span>{t}</span></div>\n'
        tw += f'tl.fromTo("#c{k} span",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.2,ease:"power2.out"}},{st:.2f});\n'

html = f'''<!doctype html>
<html lang="zh-Hant" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1080, height=1920" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
:root {{ --ground:#0f172a; --ink:#f8fafc; --accent:#fb923c; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:1080px; height:1920px; overflow:hidden; background:var(--ground); }}
#root {{ position:relative; width:100%; height:100%; font-family:sans-serif; color:var(--ink); background:var(--ground); }}
.full {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:0 110px; text-align:center; background:var(--ground); }}
#title-card h1 {{ font-size:112px; font-weight:700; margin-bottom:48px; }}
#title-card p {{ font-size:50px; line-height:1.5; color:var(--accent); font-weight:700; }}
#outro-card h2 {{ font-size:72px; margin-bottom:56px; }}
#outro-card ul {{ list-style:none; text-align:left; font-size:44px; line-height:1.55; }}
#outro-card li {{ margin-bottom:26px; }}
#badge {{ position:absolute; left:0; right:0; top:70px; text-align:center; font-size:36px; font-weight:700; color:var(--accent); }}
#phone {{ position:absolute; left:207px; top:150px; width:666px; height:1441px; border-radius:36px; overflow:hidden; background:#fff; }}
#screen {{ width:100%; height:100%; object-fit:cover; display:block; }}
.cap {{ position:absolute; left:108px; right:108px; top:1626px; height:170px; display:flex; align-items:center; justify-content:center; text-align:center; font-size:44px; line-height:1.4; font-weight:700; text-wrap:balance; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{END:.2f}" data-width="1080" data-height="1920">
<div id="phone"><video id="screen" class="clip" src="assets/screen.mp4" muted playsinline data-start="{T0}" data-duration="{SCR:.2f}" data-track-index="1"></video></div>
<div id="badge" class="clip" data-start="{T0}" data-duration="{SCR:.2f}" data-track-index="2">示範錄影・電腦螢幕錄製・非真機</div>
<div id="title-card" class="clip full" data-start="0" data-duration="{T0}" data-track-index="6"><h1>求職情報問答</h1><p>（示範錄影，電腦螢幕錄製，非真機）</p></div>
{aud}{cap}<div id="outro-card" class="clip full" data-start="{OUT:.2f}" data-duration="4" data-track-index="6"><h2>資料來源與限制</h2><ul>
<li>・畫面是 2026 年 11 月在電腦 Chrome 用 390×844 視窗錄的，不是真手機。</li>
<li>・答案是真的 DeepSeek 回應；資料是 13 家公司的公開資料，共 344 段。</li>
<li>・評估題目和語料同源，數字只能當方向。配音是電腦合成語音。</li></ul></div>
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
tl.fromTo("#title-card h1",{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},0.1);
tl.fromTo("#title-card p",{{opacity:0}},{{opacity:1,duration:0.6}},0.6);
tl.fromTo("#outro-card h2",{{opacity:0}},{{opacity:1,duration:0.4}},{OUT:.2f});
tl.fromTo("#outro-card ul",{{opacity:0}},{{opacity:1,duration:0.5}},{OUT + 0.3:.2f});
{tw}window.__timelines["main"] = tl;
</script>
</body></html>'''
(HF / "index.html").write_text(html, encoding="utf-8")
print("total", END)

"""把錄影原檔 raw.webm 切成 7 段（對應 7 句旁白），輸出 hf/assets/screen.mp4（720x1558、30fps、無聲）。
每段 = (起, 迄, 前補秒, 後補秒)：前後補的是「定格第一／最後一格」，只為等旁白講完，畫面內容沒有被改動或拼接。
用法：python -X utf8 build_screen.py <raw.webm>"""
import json, subprocess, sys
raw = sys.argv[1]
nar = [6.597, 7.106, 9.150, 8.345, 5.622, 8.182, 10.010]
seg = [(0.3, 2.3, 0, None), (2.3, 4.9, 0, None), (4.9, 12.0, 0, None), (12.0, 18.2, 3.0, 0),
       (18.2, 24.2, 0, 0.12), (24.2, 33.9, 1.5, 0), (33.9, 43.4, 0, 1.0)]
fc, D = [], []
for i, ((a, b, ps, pe), n) in enumerate(zip(seg, nar)):
    if pe is None:  # 補到旁白講完（旁白 + 0.5 秒）
        pe = max(n + 0.5, 0) - (b - a) - ps
    pe = max(pe, 0); d = ps + (b - a) + pe; D.append(round(d, 2))
    fc.append(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS,fps=30,scale=720:1558:flags=lanczos,"
              f"tpad=start_mode=clone:start_duration={ps}:stop_mode=clone:stop_duration={pe + 0.1}[v{i}]")
    fc[-1] = fc[-1].replace(f"[v{i}]", f",trim=duration={d:.3f},setpts=PTS-STARTPTS[v{i}]")
fc.append("".join(f"[v{i}]" for i in range(7)) + "concat=n=7:v=1:a=0[o]")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-filter_complex", ";".join(fc), "-map", "[o]", "-c:v", "libx264",
                "-crf", "16", "-pix_fmt", "yuv420p", "hf/assets/screen.mp4"], check=True)
print("D =", D, "sum", round(sum(D), 2))

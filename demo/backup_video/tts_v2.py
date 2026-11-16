"""用 edge-tts 逐句合成配音（免帳號免費；稿子是公開示範稿，會送到微軟服務）。
用法：python -X utf8 tts_v2.py <輸出資料夾> [voice]  -> <輸出>/<scene>_<n>.mp3 與 durations.json（去頭尾靜音後的秒數）"""
import asyncio, json, subprocess, sys
from pathlib import Path
import edge_tts
cfg = json.loads((Path(__file__).parent / "lines_v2.json").read_text(encoding="utf-8"))
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
voice = sys.argv[2] if len(sys.argv) > 2 else cfg["voice"]
def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))
async def main():
    res = {}
    for sc, lines in cfg["scenes"].items():
        for i, t in enumerate(lines):
            raw = out / f"raw_{sc}_{i}.mp3"; fin = out / f"{sc}_{i}.mp3"
            await edge_tts.Communicate(t, voice, rate=cfg["rate"]).save(str(raw))
            sil = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"{sil},areverse,{sil},areverse", str(fin)], check=True)
            raw.unlink(); res[f"{sc}_{i}"] = round(dur(fin), 3)
    (out / "durations.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(res, "sum", round(sum(res.values()), 1))
asyncio.run(main())

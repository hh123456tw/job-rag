"""第 3 版配音：edge-tts，zh-TW-YunJheNeural（雲哲），語速 -8%，逐句合成（免帳號免費；稿子是公開示範稿，會送到微軟服務）。
用法：python -X utf8 tts_v3.py <輸出資料夾>  -> <輸出>/<scene>_<n>.mp3 與 durations.json（去頭尾靜音後的秒數）
念法：plan_v3.py 的每句可寫 (字幕, 念法)；沒寫念法就把字幕去掉 [[ ]] 後，套用 SPEAK（英文縮寫改成字母間隔，數字用中文念法）。"""
import asyncio, json, re, subprocess, sys
from pathlib import Path
import edge_tts
sys.path.insert(0, str(Path(__file__).parent))
from plan_v3 import PLAN, SPEAK
VOICE, RATE = "zh-TW-YunJheNeural", "-8%"

def cap_of(x): return re.sub(r"\[\[|\]\]", "", x[0] if isinstance(x, tuple) else x)
def say_of(x):
    s = x[1] if isinstance(x, tuple) and x[1] else cap_of(x)
    for k, v in SPEAK.items(): s = s.replace(k, v)
    return s
def dur(p): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))

async def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True); res = {}
    for p in PLAN:
        for i, t in enumerate(p["text"]):
            raw = out / f"raw_{p['id']}_{i}.mp3"; fin = out / f"{p['id']}_{i}.mp3"
            memo = out / f"{p['id']}_{i}.txt"
            if fin.exists() and memo.exists() and memo.read_text(encoding="utf-8") == say_of(t):  # 念稿沒變就沿用，服務偶爾不穩
                res[f"{p['id']}_{i}"] = round(dur(fin), 3); print(p["id"], i, "沿用", res[f"{p['id']}_{i}"]); continue
            for k in range(8):  # 服務偶爾回傳沒有音訊：等一下重試
                try: await edge_tts.Communicate(say_of(t), VOICE, rate=RATE).save(str(raw)); break
                except edge_tts.exceptions.NoAudioReceived:
                    if k == 7: raise
                    await asyncio.sleep(3)
            memo.write_text(say_of(t), encoding="utf-8")
            sil = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"{sil},areverse,{sil},areverse", str(fin)], check=True)
            raw.unlink(); res[f"{p['id']}_{i}"] = round(dur(fin), 3)
            print(p["id"], i, res[f"{p['id']}_{i}"], say_of(t))
    (out / "durations.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("sum", round(sum(res.values()), 1))
if __name__ == "__main__": asyncio.run(main())

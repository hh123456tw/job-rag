"""產生 PWA 圖示（static/icon-*.png）：強調色底＋白色放大鏡。python scripts/make_icons.py
只用 Pillow（已安裝，不新增依賴）。放大鏡畫在中央 60% 內，遮罩圖示（maskable）裁成圓形也不會被切到。"""
from pathlib import Path

from PIL import Image, ImageDraw

ACC, FG = "#1d4ed8", "#ffffff"  # 同 job_rag/ui.py 的 --acc、--on-acc（淺色）
OUT = Path(__file__).resolve().parent.parent / "static"


def icon(size: int) -> Image.Image:
    s = size * 4  # 4 倍繪製再縮小，邊緣較平滑
    im = Image.new("RGB", (s, s), ACC)
    d = ImageDraw.Draw(im)
    r, w = s * 0.17, s * 0.065  # 鏡片半徑、線寬
    cx = cy = s * 0.44
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=FG, width=round(w))
    a = r * 0.7071 + w * 0.1  # 手柄從鏡片右下 45 度往外
    d.line([cx + a, cy + a, s * 0.68, s * 0.68], fill=FG, width=round(w * 1.1))
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for n in (180, 192, 512):
        icon(n).save(OUT / f"icon-{n}.png", optimize=True)
        print(f"icon-{n}.png")

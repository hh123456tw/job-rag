"""錄製備援影片素材：390x844 手機尺寸、展示模式，連本機服務。存取碼從環境變數 JOB_RAG_KEY 讀，不寫進檔案。
用法：JOB_RAG_KEY=... python -X utf8 demo/record_demo.py <輸出資料夾> [公司名，預設叡揚資訊]
輸出：<輸出資料夾>/raw.webm、events.json（各步驟的影片秒數）。答案要真的出現才算成功，否則以非零碼結束。"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
key = os.environ["JOB_RAG_KEY"]
COMPANY = sys.argv[2] if len(sys.argv) > 2 else "叡揚資訊"
TAP = """document.addEventListener('pointerdown',function(e){var d=document.createElement('div');
d.style.cssText='position:fixed;z-index:99999;pointer-events:none;width:44px;height:44px;border-radius:50%;background:rgba(255,120,0,.35);border:2px solid #f60;left:'+(e.clientX-22)+'px;top:'+(e.clientY-22)+'px;transition:all .5s;opacity:1';
document.body.appendChild(d);requestAnimationFrame(function(){d.style.transform='scale(1.8)';d.style.opacity='0'});setTimeout(function(){d.remove()},600)},true)"""
ev = []
t0 = None
def mark(name):
    ev.append({"t": round(time.time() - t0, 2), "name": name}); print(ev[-1])

def ask_and_wait(pg, q):
    pg.click("#qi"); pg.type("#qi", q, delay=140); mark("typed " + q); pg.wait_for_timeout(500)
    pg.click("#bar .go"); mark("sent")
    pg.wait_for_function("()=>{var m=document.querySelectorAll('.msg.bot');var l=m[m.length-1];return l&&l.querySelector('.chips')&&!l.querySelector('.typing')}", timeout=60000)
    last = pg.locator(".msg.bot").last
    ok = last.locator(".answer").count() > 0 and last.locator(".err").count() == 0
    mark("answered ok=%s" % ok)
    ev[-1]["bbox"] = last.locator(".answer").bounding_box()
    if not ok: print("BAD:", last.inner_text()[:300]); sys.exit(2)
    print("ANSWER:", last.locator(".answer").inner_text())

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    c = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, color_scheme="light", device_scale_factor=2,
                      record_video_dir=str(out), record_video_size={"width": 780, "height": 1688})
    c.add_init_script(TAP)
    pg = c.new_page(); t0 = time.time()
    pg.goto(BASE + "/?k=" + key); pg.goto(BASE + "/")  # 第二次載入：網址不帶存取碼
    assert "展示模式" in pg.inner_text("body"), "不是展示模式"
    mark("home"); pg.wait_for_timeout(2500)
    pg.get_by_text(COMPANY).first.tap(); mark("company"); pg.wait_for_timeout(3000)
    ask_and_wait(pg, "薪水多少？"); pg.wait_for_timeout(3500)
    cite = pg.locator(".msg.bot").last.locator(".answer .cite")
    if cite.count(): ev.append({"t": round(time.time() - t0, 2), "name": "cite bbox", "bbox": cite.first.bounding_box()}); cite.first.tap(); mark("cite1")
    pg.wait_for_timeout(2500)
    pg.locator(".msg.bot").last.locator("details.raw").scroll_into_view_if_needed()
    pg.wait_for_timeout(3500); mark("raw shown")
    pg.get_by_text("← 公司清單").tap(); pg.wait_for_timeout(1500)
    pg.get_by_text("全部公司").first.tap(); mark("all companies"); pg.wait_for_timeout(2500)
    ask_and_wait(pg, "哪些公司用 Python？"); pg.wait_for_timeout(3000)
    pg.mouse.wheel(0, 300); pg.wait_for_timeout(3500); mark("cross read")
    pg.goto(BASE + "/about"); mark("about"); pg.wait_for_timeout(2500)
    pg.locator("#pmbtn").tap(); mark("present"); pg.wait_for_timeout(3000)
    pg.locator("#pmnext").tap(); mark("next1"); pg.wait_for_timeout(3500)
    pg.locator("#pmnext").tap(); mark("next2"); pg.wait_for_timeout(3500)
    vp = pg.video.path(); c.close(); b.close()
    os.replace(vp, out / "raw.webm"); (out / "events.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")

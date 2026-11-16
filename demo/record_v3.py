"""第 3 版錄製：390x844 手機尺寸、展示模式，連本機服務（本機直連，不需存取碼）。
用法：python -X utf8 demo/record_v3.py <輸出資料夾> [公司名，預設台灣大哥大] [all|qa|th|slides]（qa 錄完單公司與跨公司後會接著錄門檻頁；th 只錄門檻頁）
輸出：
  slides/s{n}.png   簡報各頁高解析靜態圖（dsf=3，拉近仍清楚；s6b 是第 6 頁往下捲的版本）
  frames/*.jpg + frames.txt   錄影用：不用 Playwright 內建錄影（它只錄到 1 倍解析度），改用 CDP Page.captureScreenshot 連拍（2.5 倍解析度），
                              frames.txt 是 ffmpeg concat 清單（每格停留秒數），events.json 與它共用同一個時鐘
  events.json       各步驟的秒數與元素位置
真 DeepSeek 呼叫 2 次（單公司「薪水多少？」、跨公司「哪些公司用 Python？」）；答案沒出現就以非零碼結束，不剪接。
/threshold 頁只讀輸出檔，不呼叫模型。"""
import asyncio, base64, json, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5000"
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
COMPANY = sys.argv[2] if len(sys.argv) > 2 else "台灣大哥大"
PART = sys.argv[3] if len(sys.argv) > 3 else "all"  # all／qa（首頁、單公司、跨公司，會呼叫 DeepSeek）／th（只錄門檻頁，不呼叫模型）／slides（只拍簡報圖）
import os
DRY = os.environ.get("JOB_RAG_DRY") == "1"  # 試跑用：不送問題（不呼叫 DeepSeek），只驗證操作流程
SCALE = 2.5  # 影格解析度倍數（390x844 CSS px → 975x2110）；用 deviceScaleFactor 而非 clip.scale，因為 clip 用的是整頁座標，捲動後會拍到空白
ARGS = ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-features=CalculateNativeWinOcclusion"]
TAP = """document.addEventListener('pointerdown',function(e){var d=document.createElement('div');
d.style.cssText='position:fixed;z-index:99999;pointer-events:none;width:44px;height:44px;border-radius:50%;background:rgba(255,120,0,.35);border:2px solid #f60;left:'+(e.clientX-22)+'px;top:'+(e.clientY-22)+'px;transition:all .5s;opacity:1';
document.body.appendChild(d);requestAnimationFrame(function(){d.style.transform='scale(1.8)';d.style.opacity='0'});setTimeout(function(){d.remove()},600)},true)"""
ev = []; t0 = 0.0; calls = 0
def mark(name, **kw):
    ev.append({"t": round(time.perf_counter() - t0, 2), "name": name, **kw}); print(ev[-1])

async def smooth(pg, y): await pg.evaluate("y=>window.scrollTo({top:y,behavior:'smooth'})", y)

async def ask_and_wait(pg, q):
    global calls
    if DRY: return
    await pg.click("#qi"); await pg.type("#qi", q, delay=140); mark("typed " + q); await pg.wait_for_timeout(500)
    await pg.click("#bar .go"); calls += 1; mark("sent")
    await pg.wait_for_function("()=>{var m=document.querySelectorAll('.msg.bot');var l=m[m.length-1];return l&&l.querySelector('.chips')&&!l.querySelector('.typing')}", timeout=90000)
    last = pg.locator(".msg.bot").last
    ok = await last.locator(".answer").count() > 0 and await last.locator(".err").count() == 0
    mark("answered ok=%s" % ok, bbox=await last.locator(".answer").bounding_box() if ok else None)
    if not ok: print("BAD:", (await last.inner_text())[:300]); sys.exit(2)
    print("ANSWER:", await last.locator(".answer").inner_text())

async def slides(p):
    b = await p.chromium.launch(channel="chrome", args=ARGS)
    c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=3)
    pg = await c.new_page(); (out / "slides").mkdir(exist_ok=True)
    await pg.goto(BASE + "/about"); n = await pg.locator(".slide").count()
    for i in range(1, n + 1):
        await pg.goto(BASE + f"/about#{i}"); await pg.reload(); await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(out / "slides" / f"s{i}.png"))
        if i == 6:  # 第 6 頁的第 3 張卡被底下導覽列遮住一半，再拍一張往下捲的
            await pg.evaluate("window.scrollTo(0, 330)"); await pg.wait_for_timeout(300); await pg.screenshot(path=str(out / "slides" / "s6b.png"))
    await c.close(); await b.close()

async def record(p):
    global t0
    b = await p.chromium.launch(channel="chrome", args=ARGS)
    c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, color_scheme="light", device_scale_factor=SCALE)
    await c.add_init_script(TAP)
    pg = await c.new_page(); await pg.bring_to_front(); cdp = await c.new_cdp_session(pg)
    fdir = out / "frames"; fdir.mkdir(exist_ok=True)
    for f in fdir.glob("*.jpg"): f.unlink()
    stamps = []; run = True
    async def grab():
        nonlocal cdp
        while run:
            t = time.perf_counter()
            try:  # 換頁（導覽）時，進行中的截圖可能永遠不回來：逾時就重開 CDP 連線再拍
                r = await asyncio.wait_for(cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 88, "captureBeyondViewport": False}), 1.5)
            except Exception:
                cdp = await c.new_cdp_session(pg); continue
            (fdir / f"{len(stamps):05d}.jpg").write_bytes(base64.b64decode(r["data"])); stamps.append(t)
            await asyncio.sleep(max(0.0, 0.04 - (time.perf_counter() - t)))  # 最多約 25 格/秒
    await pg.goto(BASE + ("/threshold" if PART == "th" else "/"))
    if PART != "th": assert "展示模式" in await pg.inner_text("body"), "不是展示模式"
    t0 = time.perf_counter(); task = asyncio.create_task(grab())
    if PART in ("all", "qa"):
        mark("home"); await pg.wait_for_timeout(3500)
        await pg.get_by_text(COMPANY).first.tap(); mark("company"); await pg.wait_for_timeout(3200)
        await ask_and_wait(pg, "薪水多少？"); await pg.wait_for_timeout(3500)
        cite = pg.locator(".msg.bot").last.locator(".answer .cite")
        if await cite.count(): mark("cite bbox", bbox=await cite.first.bounding_box()); await cite.first.tap(); mark("cite1")
        await pg.wait_for_timeout(2500)
        if not DRY: await pg.locator(".msg.bot").last.locator("details.raw").scroll_into_view_if_needed()
        await pg.wait_for_timeout(3500); mark("raw shown")
        await pg.get_by_text("← 公司清單").tap(); await pg.wait_for_timeout(1500)
        await pg.get_by_text("全部公司").first.tap(); mark("all companies"); await pg.wait_for_timeout(2500)
        await ask_and_wait(pg, "哪些公司用 Python？"); await pg.wait_for_timeout(3000)
        for k in range(3):  # 聊天串是 #thread 在捲動，不是整頁；分三次慢慢往下讀
            await pg.evaluate("()=>{var T=document.getElementById('thread');T.scrollTo({top:T.scrollTop+300,behavior:'smooth'})}"); mark(f"cross scroll {k} start"); await pg.wait_for_timeout(2600)
        mark("cross read")
    # 門檻頁
    if PART != "th": await pg.goto(BASE + "/threshold")
    await pg.wait_for_timeout(500); mark("th top", nums=await pg.inner_text(".t-nums")); await pg.wait_for_timeout(3500)
    await smooth(pg, 250); mark("th scroll start"); await pg.wait_for_timeout(1500); mark("th chart")
    bb = await pg.locator("#sl").bounding_box(); y = bb["y"] + bb["height"] / 2
    x_of = lambda v: bb["x"] + 8 + (v - 0.40) / 0.50 * (bb["width"] - 16)
    await pg.mouse.move(x_of(0.70), y); await pg.mouse.down(); mark("drag start")
    for k in range(1, 21): await pg.mouse.move(x_of(0.70 - 0.10 * k / 20), y); await pg.wait_for_timeout(70)
    mark("dragged low", nums=await pg.inner_text(".t-nums"), ts=await pg.inner_text("#ts")); await pg.wait_for_timeout(2200)
    for k in range(1, 21): await pg.mouse.move(x_of(0.60 + 0.10 * k / 20), y); await pg.wait_for_timeout(70)
    await pg.mouse.up(); mark("dragged back", nums=await pg.inner_text(".t-nums"), ts=await pg.inner_text("#ts")); await pg.wait_for_timeout(1500)
    # 點一個點：叡揚資訊特休（檢索放行、答案層回「查無」）
    idx = await pg.evaluate("""()=>{var a=[].slice.call(document.querySelectorAll('g.pt'));
      for(var i=0;i<a.length;i++){a[i].dispatchEvent(new MouseEvent('click',{bubbles:true}));if(/特休/.test(document.getElementById('card').innerText))return i}return -1}""")
    assert idx >= 0, "找不到特休那題"
    await smooth(pg, 250); await pg.wait_for_timeout(1500)
    box = await pg.locator("g.pt").nth(idx).bounding_box(); mark("pt bbox", idx=idx, bbox=box)
    await pg.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); await pg.wait_for_timeout(600)
    mark("point tapped", card=(await pg.inner_text("#card"))[:300]); await pg.wait_for_timeout(4200)
    mark("card shown", bbox=await pg.locator("#card").bounding_box())
    await pg.evaluate("()=>{var h=[].slice.call(document.querySelectorAll('h2')).find(function(e){return e.textContent==='兩層把關'});window.scrollTo({top:h.getBoundingClientRect().top+scrollY-30,behavior:'smooth'})}")
    mark("layers scroll start"); await pg.wait_for_timeout(1500); mark("layers"); await pg.wait_for_timeout(5500)
    mark("end"); run = False; await task
    await c.close(); await b.close()
    # 影格清單：每格停留到下一格出現
    lines = []
    for i, t in enumerate(stamps):
        nxt = stamps[i + 1] if i + 1 < len(stamps) else t + 0.05
        lines.append(f"file 'frames/{i:05d}.jpg'\nduration {max(nxt - t, 0.001):.4f}")
    lines.append(f"file 'frames/{len(stamps) - 1:05d}.jpg'")
    (out / "frames.txt").write_text("\n".join(lines), encoding="utf-8")
    # 影格時間戳以 t0 為零點，和 events.json 同一個時鐘：第一格相對 t0 的偏移要記下來
    (out / "events.json").write_text(json.dumps({"first_frame_offset": round(stamps[0] - t0, 3), "events": ev}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("FRAMES", len(stamps), "fps", round(len(stamps) / (stamps[-1] - stamps[0]), 1), "DEEPSEEK_CALLS", calls)

async def main():
    async with async_playwright() as p:
        if PART in ("all", "slides"): await slides(p)
        if PART != "slides": await record(p)
try:
    asyncio.run(main())
except Exception as e:  # 收尾時 Playwright 可能報「連線已關閉」；影格與 events.json 在這之前已寫好
    print("收尾錯誤（已忽略）：", repr(e)[:120])

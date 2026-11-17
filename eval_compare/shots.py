import re, sys
from playwright.sync_api import sync_playwright
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    for name, path in (("about", "/about"), ("threshold", "/threshold"), ("home", "/")):
        r = pg.goto("http://127.0.0.1:5140" + path, wait_until="networkidle")
        pg.wait_for_timeout(800)
        pg.screenshot(path=f"eval_compare/shot_{name}.png")
        t = pg.inner_text("body")
        out[name] = (r.status, len(t), t)
        print(name, r.status, len(t), "overflowX", pg.evaluate("document.documentElement.scrollWidth>innerWidth"))
    print("errors", errs)
    open("dist/logs/pagetext.txt", "w", encoding="utf-8").write("\n=====\n".join(f"{k}\n{v[2]}" for k, v in out.items()))
    b.close()

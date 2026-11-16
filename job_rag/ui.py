"""三種畫面（問答頁、專案說明頁、準備中）共用的簡約樣式與外框。全部內嵌，不載入任何外部資源。"""

# 一個強調色（--acc）＋中性色；錯誤紅（--err）只用在失敗訊息。顏色只在 :root 定義，其餘一律用變數。
CSS = """:root{--bg:#fafaf9;--fg:#1c1c1e;--mute:#5c5f66;--line:#dcdcd8;--card:#f1f1ee;--acc:#1d4ed8;--on-acc:#fff;--err:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#121316;--fg:#ececee;--mute:#a3a6ae;--line:#30333a;--card:#1b1d22;--acc:#8ab4ff;--on-acc:#0b1220;--err:#ff9aa5}}
*{box-sizing:border-box}html{color-scheme:light dark;-webkit-text-size-adjust:100%}
body{font:16px/1.7 system-ui,-apple-system,"Segoe UI","PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;
max-width:820px;margin:0 auto;padding:0 20px 56px;background:var(--bg);color:var(--fg);overflow-wrap:anywhere}
a{color:var(--acc);text-underline-offset:3px}
nav{display:flex;gap:20px;font-size:15px;color:var(--mute);padding-top:4px}
nav a,nav b{display:inline-flex;align-items:center;min-height:44px}nav b{color:var(--fg)}
h1{font-size:1.75rem;line-height:1.3;font-weight:650;margin:12px 0 28px}
h2{font-size:1.15rem;font-weight:650;margin:40px 0 12px}
h3{font-size:.875rem;font-weight:600;color:var(--mute);margin:32px 0 12px}
.row,.grid{display:grid;gap:8px}.row{grid-template-columns:1fr}
.grid{grid-template-columns:repeat(auto-fill,minmax(var(--m,104px),1fr))}.faq{--m:140px}
button{min-height:44px;padding:0 8px;white-space:nowrap;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:10px;cursor:pointer;transition:background-color .15s,border-color .15s}
button:hover{border-color:var(--acc)}
.sel,.go{background:var(--acc);border-color:var(--acc);color:var(--on-acc);font-weight:600}.sel:hover,.go:hover{opacity:.9}
.demo{white-space:normal;text-align:left;padding:10px 14px;line-height:1.5}
.ask{display:flex;gap:8px}.ask input{flex:1;min-width:0}.ask .go{padding:0 22px}
input{width:100%;min-height:48px;padding:0 14px;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:10px;scroll-margin-block:96px}
:is(a,button,input):focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.hit,.ans,.case{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
.hit b{font-weight:600}.hit pre,.ans pre{font:inherit;line-height:1.65;white-space:pre-wrap;margin:8px 0 0}
.dim{opacity:.65}.ans ul{margin:8px 0 0;padding-left:20px;color:var(--mute);font-size:.9rem}
small{display:block;color:var(--mute);font-size:.875rem;margin-top:8px}
.warn{border-left:3px solid var(--fg);padding:4px 0 4px 14px;margin:16px 0}
.err{color:var(--err);font-weight:600}.mute{color:var(--mute)}
.link a{display:inline-flex;align-items:center;min-height:44px}
.flow{display:grid;gap:22px;list-style:none;padding:0;margin:0}
.flow li{position:relative;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0}
.flow li+li::before{content:"\\2193";position:absolute;left:14px;top:-21px;color:var(--mute);line-height:20px}
.flow b{display:block;font-size:.95rem;line-height:1.4}.flow small{margin-top:4px;font-size:.8125rem;line-height:1.45}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:8px 4px;text-align:right;vertical-align:top}th{color:var(--mute);font-weight:600;font-size:.875rem}
th:first-child,td:first-child{text-align:left}td small{font-size:.75rem;margin-top:0}
li{margin:6px 0}
.status{min-height:60vh;display:flex;flex-direction:column;justify-content:center}
.dot{width:10px;height:10px;border-radius:50%;background:var(--acc);animation:pulse 1.6s ease-in-out infinite}
@keyframes pulse{50%{opacity:.25}}
@media(min-width:600px){.row{grid-template-columns:repeat(2,1fr)}}
@media(min-width:720px){.flow{grid-template-columns:repeat(6,1fr);gap:16px}
.flow li+li::before{content:"\\2192";left:-14px;top:50%;transform:translateY(-50%)}}
@media(prefers-reduced-motion:reduce){*,::before{animation:none!important;transition:none!important}}"""


def page(title: str, body: str, head: str = "") -> str:
    return (f"<!doctype html><html lang=zh-Hant><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>{head}"
            f"<title>{title}</title><style>{CSS}</style>{body}")

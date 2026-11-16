"""三種畫面（問答頁、專案說明頁、準備中）共用的簡約樣式與外框。全部內嵌，不載入任何外部資源。"""

from .owner_ui import CSS as OWNER_CSS  # 自用／展示切換鈕與橘色橫幅（票 24）

# 一個強調色（--acc）＋中性色；錯誤紅（--err）只用在失敗訊息。顏色只在 :root 定義，其餘一律用變數。
CSS = """:root{--bg:#fafaf9;--fg:#1c1c1e;--mute:#5c5f66;--line:#dcdcd8;--card:#f1f1ee;--acc:#1d4ed8;--on-acc:#fff;--err:#b3261e;--warn:#f59e0b;--on-warn:#1c1c1e}
@media(prefers-color-scheme:dark){:root{--bg:#121316;--fg:#ececee;--mute:#a3a6ae;--line:#30333a;--card:#1b1d22;--acc:#8ab4ff;--on-acc:#0b1220;--err:#ff9aa5}}
*{box-sizing:border-box}html{color-scheme:light dark;-webkit-text-size-adjust:100%}
body{font:17px/1.7 system-ui,-apple-system,"Segoe UI","PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;
max-width:820px;margin:0 auto;padding:0 20px 56px;background:var(--bg);color:var(--fg);overflow-wrap:anywhere}
a{color:var(--acc);text-underline-offset:3px}
nav{display:flex;gap:20px;font-size:15px;color:var(--mute);padding-top:4px}
nav a,nav b{display:inline-flex;align-items:center;min-height:48px}nav b{color:var(--fg)}
h1{font-size:1.875rem;line-height:1.3;font-weight:650;margin:12px 0 28px}
h2{font-size:1.15rem;font-weight:650;margin:40px 0 12px}
h3{font-size:.875rem;font-weight:600;color:var(--mute);margin:32px 0 12px}
.row,.grid{display:grid;gap:10px}.row{grid-template-columns:1fr}
.grid{grid-template-columns:repeat(2,1fr)}.faq{display:grid;gap:10px}
button,.btn{min-height:48px;padding:0 10px;white-space:nowrap;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:10px;cursor:pointer;transition:background-color .15s,border-color .15s}
.btn{display:inline-flex;align-items:center;text-decoration:none}button:hover,.btn:hover{border-color:var(--acc)}
.faq button{min-height:60px;font-size:1.0625rem;text-align:left;padding:0 18px}.grid button{min-height:56px}
.sel,.go,.btn{background:var(--acc);border-color:var(--acc);color:var(--on-acc);font-weight:600}.sel:hover,.go:hover{opacity:.9}
.demo{white-space:normal;text-align:left;padding:10px 14px;line-height:1.5}
.ask{display:flex;gap:8px}.ask input{flex:1;min-width:0}.ask .go{padding:0 22px}
input{width:100%;min-height:52px;padding:0 14px;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:10px;scroll-margin-block:96px}
:is(a,button,input):focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.hit,.ans,.case{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
.hit b{font-weight:600}.hit pre,.ans pre{font:inherit;line-height:1.65;white-space:pre-wrap;margin:8px 0 0}
.dim{opacity:.65}.ans ul{margin:8px 0 0;padding-left:20px;color:var(--mute);font-size:.9rem}
small{display:block;color:var(--mute);font-size:.875rem;margin-top:8px}
.warn{border-left:3px solid var(--fg);padding:4px 0 4px 14px;margin:16px 0}
.err{color:var(--err);font-weight:600}.mute{color:var(--mute)}
.link a{display:inline-flex;align-items:center;min-height:48px}
nav.top{padding-top:0}.sub{color:var(--mute);margin:-16px 0 24px}.q{font-size:1.125rem;font-weight:600;margin:4px 0 16px}
summary{display:flex;align-items:center;min-height:48px;cursor:pointer;font-weight:600}
.more{margin-top:32px}.more summary{color:var(--mute);font-weight:500}
footer{margin-top:40px}footer a{display:inline-flex;align-items:center;min-height:48px}
#answer{border-color:var(--acc);border-width:2px}#answer>b{display:block;margin-bottom:6px}#ans-body{margin:0;font-size:1.0625rem}
.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;list-style:none;padding:0;margin:0;counter-reset:f}
.flow li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0}
.flow li::before{counter-increment:f;content:counter(f);display:block;color:var(--acc);font-weight:700;font-size:.875rem}
.flow b{display:block;font-size:.95rem;line-height:1.4}.flow small{display:block;margin-top:4px;font-size:.8125rem;line-height:1.45}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid var(--line);padding:8px 4px;text-align:right;vertical-align:top}th{color:var(--mute);font-weight:600;font-size:.875rem}
th:first-child,td:first-child{text-align:left}td small{font-size:.75rem;margin-top:0}
li{margin:6px 0}
.status{min-height:60vh;display:flex;flex-direction:column;justify-content:center}
.dot{width:10px;height:10px;border-radius:50%;background:var(--acc);animation:pulse 1.6s ease-in-out infinite}
@keyframes pulse{50%{opacity:.25}}
.cards{display:grid;gap:10px}.card{display:flex;flex-direction:column;justify-content:center;min-height:64px;padding:10px 18px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--fg);text-decoration:none}
.card b{font-size:1.125rem}.card span{color:var(--mute);font-size:.9375rem}.card:hover,.card:focus-visible{border-color:var(--acc)}.card.all{border-style:dashed}
body.chat{max-width:820px;height:100vh;height:100dvh;margin:0 auto;padding:0;display:flex;flex-direction:column;overflow:hidden}
.chat>header{display:flex;align-items:center;gap:4px;padding:0 12px;padding-top:env(safe-area-inset-top);border-bottom:1px solid var(--line)}
.chat>header a{display:inline-flex;align-items:center;min-height:48px;padding:0 6px;font-size:.9375rem;white-space:nowrap}
.chat .app{flex:1;text-align:center;font-size:1.0625rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#help{min-width:48px;padding:0;border-radius:999px;font-weight:700;color:var(--acc);border-color:var(--acc)}
#thread{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:16px;display:flex;flex-direction:column;gap:14px}
.msg{max-width:88%;padding:12px 16px;border-radius:18px;overflow-wrap:anywhere}.msg p{margin:0}.msg p+p{margin-top:8px}
.msg.bot{align-self:flex-start;background:var(--card);border:1px solid var(--line);border-bottom-left-radius:6px}
.msg.me{align-self:flex-end;background:var(--acc);color:var(--on-acc);border-bottom-right-radius:6px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chip{min-height:48px;padding:6px 16px;white-space:normal;text-align:left;border-radius:999px;color:var(--acc);border-color:var(--acc)}
.steps{margin-bottom:6px}.step{font-size:.9375rem;color:var(--mute);line-height:1.5}.step::before{content:"\\203A  "}
.body .answer{white-space:pre-wrap;margin:4px 0 0}.src{margin:8px 0 0;padding-left:20px;color:var(--mute);font-size:.9375rem}
.raw{margin-top:10px}.raw .hit{background:var(--bg);margin:8px 0}.raw pre{font:inherit;white-space:pre-wrap;margin:6px 0 0;line-height:1.6}
.hh{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:4px;font-size:.8125rem;color:var(--mute)}
.sc{padding:0 8px;border:1px solid var(--line);border-radius:999px;font-variant-numeric:tabular-nums;white-space:nowrap}.sc.lo{border-style:dashed;color:var(--err)}
.cite{display:inline;min-height:0;padding:.25em .3em;margin:-.25em -.1em;border:0;background:none;color:var(--acc);font:inherit;font-weight:600;text-decoration:underline;text-underline-offset:3px;touch-action:manipulation}
.src .cite{font-weight:400;text-align:left;white-space:normal}
.hit.flash{opacity:1;outline:2px solid var(--acc);outline-offset:2px}.raw .hit{transition:outline-color .3s}
.typing{display:inline-flex;gap:5px;padding:6px 0}.typing i{width:8px;height:8px;border-radius:50%;background:var(--mute);animation:pulse 1.2s ease-in-out infinite}.typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}
#bar{display:flex;gap:8px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));border-top:1px solid var(--line);background:var(--bg)}
#bar input{flex:1}#bar .go{min-width:76px}
.lead{font-size:1.1875rem;line-height:1.7}.plain{padding-left:20px}.plain li{margin:12px 0}
.level{display:grid;gap:16px;margin:24px 0 0}.level h3{margin:0 0 4px}.level .plain li{margin:6px 0}.stats{display:grid;gap:12px;margin:20px 0 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.stat b{display:block;font-size:2.25rem;line-height:1.2;color:var(--acc);font-variant-numeric:tabular-nums}.stat span{display:block;margin-top:4px}
.bars{list-style:none;padding:0;margin:16px 0}.bars li{display:grid;grid-template-columns:1fr auto;gap:4px 12px;align-items:center;margin:14px 0}
.bars .lab{grid-column:1/-1;font-weight:600}.bars small{display:inline;margin-left:8px;font-size:.875rem;font-weight:400}
.track{height:16px;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}.track i{display:block;height:100%;background:var(--acc)}
.bars b{font-variant-numeric:tabular-nums}.bars em{font-style:normal;color:var(--acc);font-weight:600}
@media(min-width:600px){.row{grid-template-columns:repeat(2,1fr)}.stats{grid-template-columns:repeat(3,1fr)}.level{grid-template-columns:3fr 2fr}}
@media(prefers-reduced-motion:reduce){*,::before{animation:none!important;transition:none!important}}"""


# PWA：只有 manifest 與 meta，沒有 service worker（查詢需要後端，離線快取只會造成舊內容）。
# theme-color 的色碼要與 CSS 的 --bg 相同（淺、深各一）；tests/test_pwa.py 會核對 manifest 的色碼。
PWA_HEAD = ("<link rel=manifest href=/manifest.webmanifest>"
            "<meta name=theme-color content='#fafaf9' media='(prefers-color-scheme: light)'>"
            "<meta name=theme-color content='#121316' media='(prefers-color-scheme: dark)'>"
            "<meta name=apple-mobile-web-app-capable content=yes>"
            "<meta name=mobile-web-app-capable content=yes>"
            "<meta name=apple-mobile-web-app-status-bar-style content=default>"  # default：狀態列跟隨頁面底色（淺深都可讀）
            "<link rel=apple-touch-icon href=/static/icon-180.png>")


def page(title: str, body: str, head: str = "") -> str:
    return (f"<!doctype html><html lang=zh-Hant><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>{PWA_HEAD}{head}"
            f"<title>{title}</title><style>{CSS}{OWNER_CSS}</style>{body}")

"""自用／展示切換的畫面（票 24）：頁首切換鈕、密碼欄、橘色橫幅。只在有設本人密碼時才會輸出。
腳本只用 textContent；密碼用 POST（JSON body）送出，不進網址。"""

BANNER = "自用模式：資料會送到 DeepSeek，請勿給別人看"
LABEL = {"demo": "展示", "self": "自用"}

CSS = """[hidden]{display:none!important}
.selfbar{background:var(--warn);color:var(--on-warn);font-weight:650;text-align:center;padding:8px 12px;font-size:.9375rem;line-height:1.4}
.modebar{display:flex;align-items:center;gap:8px;padding:6px 12px;font-size:.875rem;color:var(--mute)}
.modebar .seg{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}
.modebar button{min-height:40px;min-width:64px;border:0;border-radius:0;background:var(--bg);font-size:.9375rem}
.modebar button[aria-pressed=true]{background:var(--acc);color:var(--on-acc);font-weight:700}
.modebar button[data-m=self][aria-pressed=true]{background:var(--warn);color:var(--on-warn)}
#pinf{display:flex;gap:8px;padding:0 12px 6px}#pinf input{flex:1;min-width:0;min-height:44px}#pinf button{min-height:44px}
#pine{margin:0;padding:0 12px;font-size:.9375rem}#pine:empty{display:none}
.priv{display:inline-block;background:var(--warn);color:var(--on-warn);border-radius:6px;padding:0 6px;font-size:.8125rem;font-weight:650;margin-right:6px}"""

JS = r"""(function(){var bar=document.getElementById('modebar');if(!bar)return;
var cur=bar.dataset.mode,f=document.getElementById('pinf'),e=document.getElementById('pine'),inp=f.querySelector('input');
function wipe(){try{for(var i=sessionStorage.length-1;i>=0;i--){var k=sessionStorage.key(i);if(k&&k.indexOf('jr_chat:self:')===0)sessionStorage.removeItem(k)}}catch(x){}}
function go(){location.replace(location.pathname)}
bar.addEventListener('click',function(ev){var b=ev.target.closest('button[data-m]');if(!b||b.dataset.m===cur)return;
if(b.dataset.m==='self'){f.hidden=false;inp.focus();return}
wipe();fetch('/api/owner/logout',{method:'POST'}).then(go,go)});
f.addEventListener('submit',function(ev){ev.preventDefault();e.textContent='';
fetch('/api/owner/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:inp.value})})
.then(function(r){return r.json().catch(function(){return{}}).then(function(j){return[r.status,j]})})
.then(function(x){inp.value='';if(x[0]===200){wipe();go()}else e.textContent=x[1].message||'登入失敗'})
.catch(function(){e.textContent='無法連線'})})})();"""


def chrome(mode: str, enabled: bool) -> str:
    """橫幅（自用模式）＋切換鈕＋密碼欄。沒設本人密碼時回空字串：畫面與以前完全相同。"""
    if not enabled:
        return ""
    on = lambda m: "true" if mode == m else "false"
    banner = f"<div class=selfbar role=status>{BANNER}</div>" if mode == "self" else ""
    return (f"{banner}<div id=modebar class=modebar data-mode={mode} role=group aria-label=模式><span>目前：{LABEL[mode]}模式</span>"
            f'<span class=seg><button type=button data-m=demo aria-pressed={on("demo")}>展示</button>'
            f'<button type=button data-m=self aria-pressed={on("self")}>自用</button></span></div>'
            '<form id=pinf hidden method=post action="/api/owner/login" autocomplete=off>'
            '<input type=password name=pin placeholder="本人密碼" aria-label="本人密碼" autocomplete=off><button class=go>進入自用</button></form>'
            f"<p id=pine class=err role=alert></p><script>{JS}</script>")

"""首頁的對話介面（票 21）：內嵌腳本，只用 textContent 組畫面；步驟列的每一行都對應真的請求或回應。"""

CHAT_JS = r"""(function(){
var B=document.body,P=JSON.parse(B.dataset.presets),scope=B.dataset.scope||'',LB=B.dataset.label,
T=document.getElementById('thread'),F=document.getElementById('bar'),I=document.getElementById('qi'),
busy=false,lastKey='',MODE=B.dataset.mode||'demo',KEY='jr_chat:'+MODE+':'+B.dataset.key,hist=[];
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function save(){try{sessionStorage.setItem(KEY,JSON.stringify({html:T.innerHTML,hist:hist}))}catch(e){}}
function hjson(){return JSON.stringify(hist.slice(-2).map(function(t){return{q:t.q.slice(0,200),a:t.a.slice(0,300),m:MODE}}))}
function wipe(){try{for(var i=sessionStorage.length-1;i>=0;i--){var k=sessionStorage.key(i);if(k&&k.indexOf('jr_chat:self:')===0)sessionStorage.removeItem(k)}}catch(e){}}
function stale(j){if(j&&j.mode&&j.mode!==MODE){wipe();T.textContent='';location.replace(location.pathname);return true}return false}
function rec(q,a){hist.push({q:q.replace(/\s+/g,' '),a:a.replace(/\s+/g,' ')});hist=hist.slice(-2)}
function sh(p){var a=p.split(' > ');a=a[a.length-1];return a.length>20?a.slice(0,20)+'…':a}
function end(){T.scrollTop=T.scrollHeight}
function noChips(){var c=T.querySelectorAll('.chips');for(var i=0;i<c.length;i++)c[i].remove()}
function msg(who){var m=el('div','msg '+who);T.appendChild(m);return m}
function chips(list){var d=el('div','chips');list.forEach(function(c){var b=el('button','chip',c[1]);b.type='button';b.dataset.k=c[0];b.dataset.q=c[2];d.appendChild(b)});return d}
function presetChips(skip){var l=P.filter(function(p){return p[0]!==skip});if(l.length<3)l=l.concat(P.filter(function(p){return p[0]===skip}));return chips(l)}
function say(text,ch){var m=msg('bot');m.appendChild(el('p',null,text));if(ch)m.appendChild(ch);end();return m}
function hint(){noChips();var m=msg('bot'),L=JSON.parse(B.dataset.hint);L.forEach(function(t){m.appendChild(el('p','hl',t))});m.appendChild(presetChips(''));end();save()}
function greet(){say(B.dataset.hello);hint()}
function api(url,p,sig){return fetch(url+'?'+new URLSearchParams(p),{signal:sig}).then(function(r){return r.json().catch(function(){return{status:'error',message:'回應格式不符'}})})}
function num(x){return typeof x==='number'&&isFinite(x)}
function scoreTag(s,t){if(!num(s)||!num(t))return null;var lo=s<t,d=3;while(d<8&&s!==t&&s.toFixed(d)===t.toFixed(d))d++;
var g=el('span','sc'+(lo?' lo':''),s.toFixed(d)+(lo?' < ':' ≥ ')+t.toFixed(d)+(lo?' 低於門檻':''));g.title='相似度分數／查無門檻（bge-m3）';return g}
function rawBox(hits,dim,open,thr){var d=el('details','raw');if(open)d.open=true;d.appendChild(el('summary',null,'看原文（'+hits.length+'）'));
hits.forEach(function(h,i){var g=scoreTag(h.score,thr),x=el('div','hit'+(dim||(g&&g.className.indexOf('lo')>0)?' dim':''));
var r=el('div','hh');r.appendChild(el('span','no','['+(i+1)+']'));if(g)r.appendChild(g);x.appendChild(r);if(h.private)x.appendChild(el('span','priv','自用資料'));x.appendChild(el('b',null,h.company+' · '+h.file+' · '+h.heading_path));x.appendChild(el('pre',null,h.text));
if(h.also_in&&h.also_in.length)x.appendChild(el('small',null,'也出現於：'+h.also_in.map(function(a){return a.file+' · '+a.heading_path}).join('；')));d.appendChild(x)});return d}
function cite(n,t){var b=el('button','cite',t);b.type='button';b.dataset.n=n;b.setAttribute('aria-label','看原文第 '+n+' 段');return b}
function cited(p,text,n){text.split(/(\[\d+\])/).forEach(function(s){var m=/^\[(\d+)\]$/.exec(s),k=m?+m[1]:0;
if(k>=1&&k<=n)p.appendChild(cite(k,s));else if(s)p.appendChild(document.createTextNode(s))})}
function srcN(s,hits){for(var i=0;i<hits.length;i++){var h=hits[i];if(h.company===s.company&&h.file===s.file&&h.heading_path===s.heading_path)return i+1}return 0}
function jump(c){var m=c.closest('.msg'),d=m&&m.querySelector('details.raw'),x=d&&d.querySelectorAll('.hit')[c.dataset.n-1];if(!x)return;
d.open=true;x.classList.add('flash');x.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
setTimeout(function(){x.classList.remove('flash')},1800)}
function secs(ms){return (ms/1000).toFixed(ms<100?3:2)+' 秒'}
function metaText(i){var p=[];if(num(i.s)&&i.s>=0)p.push('檢索 '+secs(i.s));if(num(i.a)&&i.a>=0)p.push('整理 '+secs(i.a));
var u=i.u||{},t=[];if(num(u.prompt_tokens))t.push('輸入 '+u.prompt_tokens);if(num(u.completion_tokens))t.push('輸出 '+u.completion_tokens);
if(t.length)p.push(t.join('／')+' tokens');return p.join('｜')}
function run(q){
busy=true;var info={};var HJ=hist.length?hjson():'',m=msg('bot'),steps=el('div','steps'),body=el('div','body');
function hp(p){if(HJ)p.history=HJ;return p}m.appendChild(steps);m.appendChild(body);
var dots=el('span','typing');dots.setAttribute('aria-hidden','true');dots.innerHTML='<i></i><i></i><i></i>';body.appendChild(dots);
function step(t){steps.appendChild(el('p','step',t));end()}
function done(){dots.remove();busy=false;var mt=metaText(info);if(mt)steps.appendChild(el('p','meta',mt));body.parentNode.appendChild(presetChips(lastKey));
if(m.offsetHeight>T.clientHeight)T.scrollTop=m.offsetTop-T.offsetTop-8;else end();save()}
function bad(t,box){dots.remove();body.appendChild(el('p','err',t));if(box)body.appendChild(box);done()}
step('搜尋資料（範圍：'+LB+'）');
api('/api/search',hp({q:q,company:scope||''})).then(function(j){
if(stale(j))return;if(j.status!=='ok'&&j.status!=='low'){bad(j.message||'搜尋失敗',null);return}
var hits=j.hits||[],thr=j.threshold;info.s=j.search_ms;if(j.expanded)step('問題很短，接上一題一起搜尋');if(j.detected)step('已偵測到公司：'+j.company+'，只搜這一家');
step(hits.length?'找到 '+hits.length+' 段：'+hits.map(function(h){return sh(h.heading_path)}).join('、'):'沒有找到段落');
if(j.status==='low'){dots.remove();body.appendChild(el('p',null,'我找不到很接近的內容，不確定有沒有答案。下面的原文僅供參考，請自己核對。'));
if(hits.length)body.appendChild(rawBox(hits,true,true,thr));rec(q,'（沒有找到很接近的內容）');done();return}
step('整理答案');
var c=new AbortController(),to=setTimeout(function(){c.abort()},40000);
api('/api/answer',hp({q:q,company:j.company||''}),c.signal).then(function(a){clearTimeout(to);if(stale(a))return;dots.remove();
if(a.status==='ok'){info.a=a.answer_ms;info.u=a.usage;
if(a.answer==='查無'){body.appendChild(el('p',null,'查無：語料裡沒有明確的答案。原文在下面，請自己核對。'));body.appendChild(rawBox(hits,false,true,thr));rec(q,'（資料中沒有找到答案）');done();return}
var p=el('p','answer');cited(p,a.answer,hits.length);body.appendChild(p);var u=el('ul','src');
a.sources.forEach(function(s){var t=s.company+' · '+sh(s.heading_path),k=srcN(s,hits),li=el('li');li.appendChild(k?cite(k,t):document.createTextNode(t));u.appendChild(li)});body.appendChild(u);body.appendChild(rawBox(hits,false,false,thr));rec(q,a.answer);done();return}
if(a.status==='low'){body.appendChild(el('p',null,'我找不到很接近的內容，不確定有沒有答案。'));body.appendChild(rawBox(hits,true,true,thr));rec(q,'（沒有找到很接近的內容）');done();return}
body.appendChild(el('p','err',a.message||'整理失敗。原文在下面。'));body.appendChild(rawBox(hits,false,true,thr));done()
}).catch(function(){clearTimeout(to);dots.remove();body.appendChild(el('p','err','整理失敗：逾時或無法連線。原文在下面。'));body.appendChild(rawBox(hits,false,true,thr));done()})
}).catch(function(){bad('搜尋失敗：無法連線。',null)})}
function ask(q,key){if(busy)return;lastKey=key||'';noChips();say(q).className='msg me';run(q)}
T.addEventListener('click',function(e){var c=e.target.closest('.cite');if(c){jump(c);return}var b=e.target.closest('.chip');if(!b||busy)return;ask(b.dataset.q,b.dataset.k)});
F.addEventListener('submit',function(e){e.preventDefault();var q=I.value.trim();if(!q||busy)return;I.value='';I.blur();ask(q,'')});
var H=document.getElementById('help');H.addEventListener('click',function(){if(!busy)hint()});
var old=null;try{old=JSON.parse(sessionStorage.getItem(KEY))}catch(e){}
if(old&&old.html){T.innerHTML=old.html;hist=Array.isArray(old.hist)?old.hist.filter(function(t){return t&&typeof t.q==='string'&&typeof t.a==='string'}).slice(-2):[];end()}else greet();
})();"""

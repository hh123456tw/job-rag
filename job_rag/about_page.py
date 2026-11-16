"""專案說明頁的 HTML。數字全部來自 about.load() 的輸出；純 HTML/CSS，不用圖表庫。"""
from markupsafe import escape

from . import METHODS
from .ui import page

LABEL = {"bm25": "BM25（jieba 斷詞）", "bge-small-zh": "bge-small-zh", "bge-m3": "bge-m3", "e5-large": "multilingual-e5",
         "hybrid": "混合（BM25＋bge-m3）"}
SHORT = {"bm25": "BM25", "bge-small-zh": "bge-small-zh", "bge-m3": "bge-m3", "e5-large": "e5", "hybrid": "混合"}

def _f(x):
    return f"{x:.3f}"


def _where(gold):
    more = f"（另有 {len(gold) - 1} 處）" if len(gold) > 1 else ""
    return f"{gold[0]['file']} · {gold[0]['heading']}{more}"


def _rank(r, depth):
    return f"第 {r} 名" if r else f"前 {depth} 名內沒有"


def _scores(d) -> str:
    rows = "".join(
        f"<tr><td>{escape(LABEL[r['method']])}</td>" + "".join(
            f"<td>{_f(r[k])}<small>[{_f(r['ci'][k][0])}, {_f(r['ci'][k][1])}]</small></td>" for k in ("hit@1", "hit@3", "mrr"))
        + "</tr>" for r in d["table"])
    g, c, gt = d["generation"], d["cross"], d["gate"]
    same = "同樣" if c["n"] == g["scored"] else "其中"
    verdict = "結果一致" if c["consistent"] else "結果和 RAGAS 不一致，請看輸出檔"
    failed = f"，評估失敗 {g['failed']} 題" if g["failed"] else ""
    return (
        f"<p>評分單位是段落。<b>Hit@1</b>、<b>Hit@3</b>：正確答案所在的段落（金標段落）排在前 1、前 3 名內的題數比例。"
        f"<b>MRR</b>（平均倒數名次）：正確段落排第幾，就取 1 除以名次再平均。方括號是 95% 信賴區間："
        f"把 {d['n_answerable']} 題可回答題重抽 {d['bootstrap']} 次，成績落在這個範圍。名次最多看到第 {d['depth']}。</p>"
        f"<table><tr><th>檢索方式</th><th>Hit@1</th><th>Hit@3</th><th>MRR</th></tr>{rows}</table>"
        f"<p><b>生成層（RAGAS，用 LLM 當評審的 RAG 評估工具）</b>：忠實度（答案的每個陳述，段落裡找不找得到依據）平均 {_f(g['faithfulness'])}，"
        f"答案相關性（從答案反推問題，和原問題像不像）平均 {_f(g['answer_relevancy'])}。"
        f"已評分 {g['scored']} 題；另有 {g['gated']} 題被查無門檻擋住，沒有打分{failed}。</p>"
        f"<p>另請 GPT 獨立複查{same} {c['n']} 題（不是 RAGAS）：{c['claims']} 個陳述中 {c['supported']} 個有依據，"
        f"忠實度平均 {_f(c['mean'])}，{verdict}。</p>"
        f"<p><b>查無門檻</b>（bge-m3 最高相似度 {gt['threshold']:.3f}，低於它就提示「可能沒有答案」）："
        f"不可回答題擋住 {gt['unanswerable_blocked']}/{gt['n_unanswerable']}，"
        f"可回答題誤擋 {gt['answerable_blocked']}/{gt['n_answerable']}。</p>")


def _case(c, depth) -> str:
    head = f"<b>{escape(c['question'])}</b><br>正確答案所在的段落：{escape(_where(c['gold']))}<br>"
    if c["kind"] == "miss":
        fails = "、".join(f"{SHORT[m]}（{_rank(c['ranks'][m], depth)}）" for m in c["failed_methods"])
        return (f"<div class=case>{head}{SHORT[c['best']]} 找到了（{_rank(c['best_rank'], depth)}）；"
                f"前 3 名沒找到的方式：{escape(fails)}。</div>")
    return (f"<div class=case>{head}bge-m3 其實找得到（{_rank(c['rank'], depth)}），但最高相似度 {c['score']:.3f}"
            f" 低於門檻 {c['threshold']:.3f}，被當成「可能沒有答案」。</div>")


def _cases(d) -> str:
    if not d["cases"]:
        return "<p>這次評估沒有符合條件的失敗案例。</p>"
    return ("<p class=mute>由評估輸出自動挑出：先挑「最好的方式找到、別的方式沒找到」的題，再挑「被查無門檻誤擋」的題。</p>"
            + "".join(_case(c, d["depth"]) for c in d["cases"]))


def render(data: dict | None, error: str, n_segments: int, n_companies: int) -> str:
    """data 為 None 時（輸出檔缺或過期），成績與失敗案例改顯示明確錯誤，不用舊數字。"""
    n = len(METHODS)
    err = f"<p class=err>無法顯示：{escape(error)}</p>"
    counts = f"{data['n_answerable']} 題可回答、{data['n_unanswerable']} 題不可回答" if data else "題少"
    return page("專案說明｜求職情報問答", f"""<nav><a href="/">問答</a><b>專案說明</b></nav>
<h1>求職情報問答</h1>
<section><h2>1. 這是什麼</h2>
<p>現場快速查 {n_companies} 家公司的公開資料。輸入問題，馬上看到最相關的原文段落；需要時再請 LLM（大型語言模型）整理成答案，答案附出處。</p></section>
<section><h2>2. 流程</h2>
<ol class=flow>
<li><b>公開資料</b><small>{n_companies} 家公司的公開事實</small></li>
<li><b>切段</b><small>依標題切成段落</small></li>
<li><b>檢索</b><small>找出最相關的段落</small></li>
<li><b>原文結果</b><small>前 3 段，不經過 LLM</small></li>
<li><b>整理成答案</b><small>按鈕才呼叫 LLM</small></li>
<li><b>附出處或可能沒有答案</b><small>失敗時顯示錯誤</small></li>
</ol></section>
<section><h2>3. 五個設計決定</h2><ul>
<li><b>依標題切段，每段前面加公司名與標題路徑。</b>檢索時每一段都帶著「哪家公司、哪個標題」，問句提到公司或主題時比較容易對上。</li>
<li><b>比較 {n} 種檢索方式。</b>BM25（關鍵字比對）、bge-small-zh、multilingual-e5、bge-m3（後三者是向量檢索：把文字轉成數字再比相似度）、混合（BM25 加 bge-m3，用 RRF 合併名次）。不先假設哪種好，用同一批題目量。</li>
<li><b>只用公開事實。</b>評價、判斷、風險這類不是公開事實的段落，載入時就丟掉：不進索引、不送 LLM，畫面給別人看也安全。</li>
<li><b>預設只顯示原文，按鈕才用 LLM。</b>原文結果最快，也不花 API 額度；使用者可以先自己核對原文。</li>
<li><b>沒有把握時提示「可能沒有答案」，失敗時顯示錯誤，不亂答。</b>最高相似度低於門檻就提示，並且不提供整理成答案；API 失敗時顯示錯誤，原文結果照常顯示。</li>
</ul></section>
<section><h2>4. 成績</h2>{_scores(data) if data else err}</section>
<section><h2>5. 兩個失敗案例</h2>{_cases(data) if data else err}</section>
<section><h2>6. 限制</h2><ul>
<li>{counts}。區間很寬，只能當方向。</li>
<li>題目與語料同源，沒有獨立測試題。查無門檻用同一批題挑，分數可能偏樂觀。</li>
<li>RAGAS 評審與生成同為 DeepSeek，可能偏愛自己的答案。已另用 GPT 複查，但兩者都只量「答案有沒有依據」，不量對不對。</li>
<li>資料只有 {n_segments} 段。</li>
</ul></section>""")

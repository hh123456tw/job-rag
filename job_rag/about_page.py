"""專案說明頁的 HTML。數字全部來自 about.load() 的輸出；純 HTML/CSS，不用圖表庫。"""
from markupsafe import escape

from . import METHODS
from .ui import page

LABEL = {"bm25": "BM25（jieba 斷詞）", "bge-small-zh": "bge-small-zh", "bge-m3": "bge-m3", "e5-large": "multilingual-e5",
         "hybrid": "混合（BM25＋bge-m3）"}
PLAIN = {"bm25": "關鍵字比對", "bge-small-zh": "小型向量模型", "bge-m3": "大型向量模型", "e5-large": "另一個向量模型", "hybrid": "關鍵字加向量"}
SHORT = {"bm25": "BM25", "bge-small-zh": "bge-small-zh", "bge-m3": "bge-m3", "e5-large": "e5", "hybrid": "混合"}

def _f(x):
    return f"{x:.3f}"


def _where(gold):
    more = f"（另有 {len(gold) - 1} 處）" if len(gold) > 1 else ""
    return f"{gold[0]['file']} · {gold[0]['heading']}{more}"


def _rank(r, depth):
    return f"第 {r} 名" if r else f"前 {depth} 名內沒有"


def _details(d) -> str:
    """詳細數字（預設收合）：完整成績表、查無門檻、生成層。名詞在這裡才出現，各解釋一次。"""
    rows = "".join(
        f"<tr><td>{escape(LABEL[r['method']])}</td>" + "".join(
            f"<td>{_f(r[k])}<small>[{_f(r['ci'][k][0])}, {_f(r['ci'][k][1])}]</small></td>" for k in ("hit@1", "hit@3", "mrr"))
        + "</tr>" for r in d["table"])
    g, c, gt = d["generation"], d["cross"], d["gate"]
    intro = (
        f"<p>評分單位是段落。<b>Hit@1</b>、<b>Hit@3</b>：正確段落排在第 1 名、前 3 名內的題數比例。"
        f"<b>MRR</b>（平均倒數名次）：正確段落平均排第幾名的倒數，越接近 1 越好。方括號是 95% 信賴區間："
        f"把 {d['n_answerable']} 題重抽 {d['bootstrap']} 次，成績落在這個範圍。名次最多看到第 {d['depth']}。</p>"
        f"<table><tr><th>找法</th><th>Hit@1</th><th>Hit@3</th><th>MRR</th></tr>{rows}</table>")
    gate = (f"<p><b>查無門檻</b>（bge-m3 最高相似度 {gt['threshold']:.3f}，低於它就提示「可能沒有答案」）："
            f"不可回答題擋住 {gt['unanswerable_blocked']}/{gt['n_unanswerable']}，"
            f"可回答題誤擋 {gt['answerable_blocked']}/{gt['n_answerable']}。</p>")
    if g is None:  # 公開版：沒有 DeepSeek 金鑰，沒有生成層輸出
        return intro + "<p><b>生成層（RAGAS）</b>：這份輸出沒有生成層評估（需要 DeepSeek 金鑰，見 README）。</p>" + gate
    same = "同樣" if c["n"] == g["scored"] else "其中"
    verdict = "結果一致" if c["consistent"] else "結果和 RAGAS 不一致，請看輸出檔"
    failed = f"，評估失敗 {g['failed']} 題" if g["failed"] else ""
    return (
        intro +
        f"<p><b>生成層（RAGAS，用 LLM 當評審的 RAG 評估工具）</b>：忠實度（答案的每個陳述，段落裡找不找得到依據）平均 {_f(g['faithfulness'])}，"
        f"答案相關性（從答案反推問題，和原問題像不像）平均 {_f(g['answer_relevancy'])}。"
        f"已評分 {g['scored']} 題；另有 {g['gated']} 題被查無門檻擋住，沒有打分{failed}。</p>"
        f"<p>另請 GPT 獨立複查{same} {c['n']} 題（不是 RAGAS）：{c['claims']} 個陳述中 {c['supported']} 個有依據，"
        f"忠實度平均 {_f(c['mean'])}，{verdict}。</p>" + gate)


def _stat(big, text) -> str:
    return f"<div class=stat><b>{escape(big)}</b><span>{escape(text)}</span></div>"


def _stats(d) -> str:
    """三張重點數字卡。數字全部來自評估輸出檔；沒有資料時整塊不顯示（錯誤由成績區塊說明）。"""
    if not d:
        return ""
    best = next(r for r in d["table"] if r["method"] == "bge-m3")
    gt, c = d["gate"], d["cross"]
    cards = [
        _stat(f"{best['found']} / {d['n_answerable']}", f"有答案的 {d['n_answerable']} 題裡，正確段落排進前 3 名的題數（網站實際用的找法）"),
        _stat(f"{gt['unanswerable_blocked']} / {gt['n_unanswerable']}", f"故意問沒有答案的 {gt['n_unanswerable']} 題裡，系統回「可能沒有答案」的題數"),
    ]
    cards.append(_stat(f"{c['supported']} / {c['claims']}", f"另一個 AI 複查答案：{c['claims']} 個說法裡，在原文找得到依據的個數")
                 if c else _stat("沒有", "這份輸出沒有答案品質的評估"))
    return "<div class=stats>" + "".join(cards) + "</div>"


def _bars(d) -> str:
    """各找法「正確段落排前 3 名」的題數，長的在上；並列時維持原本順序。最多的標「最好」。"""
    n = d["n_answerable"]
    rows = sorted(d["table"], key=lambda r: -r["found"])
    top = rows[0]["found"]
    return "<ul class=bars>" + "".join(
        f"<li><span class=lab>{escape(PLAIN[r['method']])}<small>{escape(SHORT[r['method']])}</small>{' <em>最好</em>' if r['found'] == top else ''}</span>"
        f"<span class=track><i style='width:{100 * r['found'] / n:.1f}%'></i></span>"
        f"<b>{r['found']} / {n}</b></li>" for r in rows) + "</ul>"


def _scores(d) -> str:
    return (f"<p>用 {d['n_answerable']} 道有答案的題目，量五種找法：正確的段落有沒有排進前 3 名。條越長越好。</p>"
            f"{_bars(d)}<details class=more><summary>看詳細數字</summary>{_details(d)}</details>")


def _case(c, depth) -> str:
    head = f"<b>{escape(c['question'])}</b><br>正確的段落在：{escape(_where(c['gold']))}<br>"
    if c["kind"] == "miss":
        fails = "、".join(f"{PLAIN[m]}（{_rank(c['ranks'][m], depth)}）" for m in c["failed_methods"])
        return (f"<div class=case>{head}{PLAIN[c['best']]}找到了（{_rank(c['best_rank'], depth)}）；"
                f"前 3 名沒找到的找法：{escape(fails)}。</div>")
    return (f"<div class=case>{head}bge-m3 其實找得到（{_rank(c['rank'], depth)}），但最高相似度 {c['score']:.3f}"
            f" 低於門檻 {c['threshold']:.3f}，被當成「可能沒有答案」。</div>")


def _cases(d) -> str:
    if not d["cases"]:
        return "<p>這次評估沒有符合條件的失敗案例。</p>"
    return ("<p class=mute>由評估輸出自動挑出：先挑「最好的方式找到、別的方式沒找到」的題，再挑「被查無門檻誤擋」的題。</p>"
            + "".join(_case(c, d["depth"]) for c in d["cases"]))


def render(data: dict | None, error: str, n_segments: int, n_companies: int) -> str:
    """data 為 None 時（輸出檔缺或過期），成績與失敗案例改顯示明確錯誤，不用舊數字。"""
    err = f"<p class=err>無法顯示：{escape(error)}</p>"
    gen_limit = ("<li>評審與生成同為 DeepSeek，可能偏愛自己的答案。已另用 GPT 複查，但兩者都只量「答案有沒有依據」，不量對不對。</li>"
                 if not data or data["generation"] else "")
    counts = f"只有 {data['n_answerable']} 題有答案、{data['n_unanswerable']} 題沒答案，只能當方向。" if data else "題目很少，只能當方向。"
    return page("專案說明｜求職情報問答", f"""<nav><a href="/">問答</a><b>專案說明</b></nav>
<h1>求職情報問答</h1>
<section><h2>1. 這是什麼</h2>
<p class=lead>點一家公司，直接問問題。答案先出現，附出處；原文收在下面，隨時可以核對。目前收 {n_companies} 家公司的公開資料。</p>
{_stats(data)}</section>
<section><h2>2. 流程</h2>
<ol class=flow>
<li><b>公開資料</b><small>{n_companies} 家公司，只收公開事實</small></li>
<li><b>切段</b><small>依標題切成小段</small></li>
<li><b>找段落</b><small>找出最相關的幾段</small></li>
<li><b>原文結果</b><small>前 3 段，收在「看原文」</small></li>
<li><b>整理答案</b><small>請 LLM（大型語言模型）整理，附出處</small></li>
<li><b>出處或「可能沒有答案」</b><small>失敗時說明原因，原文展開</small></li>
</ol></section>
<section><h2>3. 五個設計決定</h2><ul class=plain>
<li><b>依標題切段，每段前面加公司名。</b>這樣問句提到公司或主題時，比較容易對上。</li>
<li><b>比較五種找法。</b>不先假設哪種好，用同一批題目量。</li>
<li><b>只用公開事實。</b>個人意見與推測在載入時就丟掉：不進索引、不送 LLM，畫面給別人看也安全。</li>
<li><b>答案優先，失敗時回到原文。</b>先立刻顯示原文，再請 LLM 整理答案；失敗、逾時或達用量上限時，直接展開原文。</li>
<li><b>沒把握就說「可能沒有答案」。</b>最高相似度低於門檻就提示，並且不呼叫 LLM，不亂答。</li>
</ul></section>
<section><h2>4. 我比較了 5 種找法</h2>{_scores(data) if data else err}</section>
<section><h2>5. 兩個失敗案例</h2>{_cases(data) if data else err}</section>
<section><h2>6. 限制</h2><ul class=plain>
<li>{counts}</li>
<li>題目與語料同源，沒有獨立測試題。「可能沒有答案」的門檻用同一批題挑，分數可能偏樂觀。</li>
{gen_limit}
<li>資料只有 {n_segments} 段。</li>
</ul></section>""")

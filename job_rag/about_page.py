"""專案說明頁的 HTML。數字全部來自 about.load() 的輸出；純 HTML/CSS，不用圖表庫。"""
from markupsafe import escape

from . import METHODS, memory, retrieval
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


def _terms(d) -> str:
    """兩個評估名詞（MRR、RAGAS）用條列白話說明，直接顯示在成績下面，不收合。數字取自輸出檔。"""
    best = next(r for r in d["table"] if r["method"] == "bge-m3")
    lo, hi = best["ci"]["mrr"]
    g = d["generation"]
    mrr = ("<h3>MRR（平均倒數名次）</h3><ul class=plain>"
           "<li><b>量什麼：</b>正確段落排得多前面。</li>"
           f"<li><b>怎麼算：</b>每題取「1 ÷ 名次」（第 1 名 1 分、第 2 名 0.5 分、第 3 名約 0.33 分、前 {d['depth']} 名內沒有 0 分），再把所有題目平均。</li>"
           "<li><b>怎麼看：</b>越接近 1 越好。</li>"
           f"<li><b>我們的結果：</b>網站用的 bge-m3 是 {_f(best['mrr'])}（95% 區間 {_f(lo)}–{_f(hi)}）。</li></ul>")
    if g is None:
        return mrr + "<h3>RAGAS</h3><ul class=plain><li>用另一個語言模型當評審、替答案打分的評估工具。這份輸出沒有生成層評估（需要 DeepSeek 金鑰，見 README）。</li></ul>"
    return (mrr + "<h3>RAGAS</h3><ul class=plain>"
            "<li><b>量什麼：</b>答案好不好（不是段落找得準不準）。是用另一個語言模型當評審的開源評估工具。</li>"
            f"<li><b>忠實度 {_f(g['faithfulness'])}：</b>答案的每個說法，在給它的段落裡找得到依據。</li>"
            f"<li><b>答案相關性 {_f(g['answer_relevancy'])}：</b>答案有回答到問題。</li>"
            f"<li><b>範圍：</b>共評分 {g['scored']} 題。評審和生成同為 DeepSeek，可能偏愛自己的答案，所以另請 GPT 複查。</li></ul>")


def _level(d) -> str:
    """「RAG 程度一眼看」：做了什麼、刻意沒做什麼。數字取自輸出檔與程式常數；沒做的項目是專案實際沒有的功能。"""
    if not d:
        return ""
    best = next(r for r in d["table"] if r["method"] == "bge-m3")
    lo, hi = best["ci"]["mrr"]
    g, c = d["generation"], d["cross"]
    done = [
        "依標題切段，答案附出處與引用編號",
        f"比較 {len(METHODS)} 種找法（關鍵字、向量、混合），用同一批題目量",
        f"檢索評估：MRR {_f(best['mrr'])}（95% 區間 {_f(lo)}–{_f(hi)}）",
        f"沒把握就不亂答：最高相似度低於 {retrieval.NOT_FOUND_THRESHOLD:.3f} 不呼叫 LLM",
    ]
    if g:
        done.append(f"答案評估：RAGAS 忠實度 {_f(g['faithfulness'])}、答案相關性 {_f(g['answer_relevancy'])}")
    if c:
        done.append(f"換一個 AI 獨立複查：{c['claims']} 個說法中 {c['supported']} 個有依據")
    done.append(f"追問記憶：帶入最近 {memory.MAX_TURNS} 輪（簡單規則）")
    undone = ["重排序模型（reranker）", "向量資料庫（資料只有數百段，在記憶體內搜尋就夠）", "微調模型",
              "線上監控與使用者回饋", "獨立測試題（題目與語料同源）"]

    def li(xs):
        return "".join(f"<li>{escape(x)}</li>" for x in xs)
    return (f"<div class=level><div><h3>做了</h3><ul class=plain>{li(done)}</ul></div>"
            f"<div><h3>刻意沒做</h3><ul class=plain>{li(undone)}</ul></div></div>")


def _arch(n_segments: int, n_companies: int) -> str:
    """系統架構圖：純 HTML／CSS。方框文字取自程式常數與載入結果，每個方框都對得上程式（tests/test_about_eng.py）。"""
    r = retrieval

    def box(t, x):
        return f"<li class=box><b>{escape(t)}</b><small>{escape(x)}</small></li>"

    def chain(items):
        return "<ol class=pipe>" + "".join(box(*i) for i in items) + "</ol>"
    main = [("公開資料", f"{n_companies} 家、{n_segments} 段公開事實段落"),
            ("切段", f"依標題切；太長再切（約 {r.CHUNK} 字、重疊 {r.OVERLAP} 字）"),
            ("向量", f"{r.DEFAULT_METHOD}，本機載入，不連網"),
            ("索引", "FAISS（IndexFlatIP，記憶體內）"),
            (f"取前 K 段", f"K = {r.DEFAULT_K}，前 {r.DEFAULT_K} 段原文先顯示"),
            ("查無門檻", f"最高相似度低於 {r.NOT_FOUND_THRESHOLD:.3f}：不呼叫 LLM"),
            ("生成", "DeepSeek，只根據段落回答"),
            ("答案與出處", "附引用編號；失敗回到原文")]
    ev = [("評估集", "手寫題目與金標段落"), ("MRR／Hit@k", "量找法"), ("RAGAS", "量答案"), ("另一個 AI 複查", "GPT 獨立複查")]
    mode = [("展示", "預設；只有公開事實段落"), ("自用", "本人密碼通過後才開；另有本機資料")]
    return (f"<div class=arch><p class=lab>主流程</p>{chain(main)}<p class=lab>評估迴路</p>{chain(ev)}"
            f"<p class=lab>模式隔離</p>{chain(mode)}</div>")


def _eng(d, n_segments: int, n_companies: int) -> str:
    """給工程面試官的技術細節（預設收合）。附在第 4 塊底下；沒有評估資料時整塊不顯示。"""
    return ("<details class=eng><summary>給工程面試官：技術細節</summary>"
            f"<h3>系統架構</h3>{_arch(n_segments, n_companies)}</details>")


def _scores(d) -> str:
    return (f"<p>用 {d['n_answerable']} 道有答案的題目，量五種找法：正確的段落有沒有排進前 3 名。條越長越好。</p>"
            f"{_bars(d)}{_terms(d)}<details class=more><summary>看詳細數字</summary>{_details(d)}</details>")


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


def _flow(n_segments: int, n_companies: int) -> str:
    """流程 6 格：標題＋一句「我們怎麼做」。數字與參數取自程式常數與載入結果，不手寫。"""
    r = retrieval
    cells = [
        ("公開資料", f"{n_companies} 家調查筆記只留公司做什麼、職缺、技術、財務這類公開事實，共 {n_segments} 段。"),
        ("切段", f"依標題切開，每段前面加上公司名與標題；太長的再細切（約 {r.CHUNK} 字、重疊 {r.OVERLAP} 字）。"),
        ("找段落", f"用 {r.DEFAULT_METHOD} 把問題和每段轉成向量，取最相近的前 {r.DEFAULT_K} 段；選它是因為比較了 {len(METHODS)} 種找法。"),
        ("原文結果", "先把這幾段原文立刻顯示，標出公司、檔名與標題，讓人自己核對。"),
        ("整理答案", f"把這幾段交給 DeepSeek，要求只根據段落回答並附出處編號；追問會帶入最近 {memory.MAX_TURNS} 輪對話。"),
        ("出處或「可能沒有答案」", f"最高相似度低於 {r.NOT_FOUND_THRESHOLD:.3f} 就不呼叫 DeepSeek，只顯示淡色原文；呼叫失敗時也回到原文。"),
    ]
    return "<ol class=flow>" + "".join(f"<li><b>{escape(t)}</b><small>{escape(x)}</small></li>" for t, x in cells) + "</ol>"


def _memory(data) -> str:
    """對話記憶小段（票 22）。沒有輸出檔就不顯示；輸出檔有問題只在這一段顯示錯誤。"""
    if not data:
        return ""
    if data["followup_error"]:
        return f"<p class=err>對話記憶的評估無法顯示：{escape(data['followup_error'])}</p>"
    f = data["followup"]
    if not f:
        return ""
    return (f"<p><b>對話記憶。</b>對話會記住最近 2 輪（記在瀏覽器，伺服器不存）。追問很短、沒提公司名也沒提主題時，"
            f"系統把上一題的問句接在前面再搜；這是簡單規則，不用 LLM 改寫問句。追問只用 {f['n']} 題量過：正確段落排進前 3 名的題數，"
            f"不補全 {f['plain']}/{f['n']}，補全 {f['expand']}/{f['n']}（規則補全了其中 {f['expanded']} 題）。"
            f"只量了檢索，沒有量多輪答案品質；題少，只能當方向。</p>")


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
{_stats(data)}{_level(data)}</section>
<section><h2>2. 流程</h2>
{_flow(n_segments, n_companies)}</section>
<section><h2>3. 五個設計決定</h2><ul class=plain>
<li><b>依標題切段，每段前面加公司名。</b>這樣問句提到公司或主題時，比較容易對上。</li>
<li><b>比較五種找法。</b>不先假設哪種好，用同一批題目量。</li>
<li><b>只用公開事實。</b>個人意見與推測在載入時就丟掉：不進索引、不送 LLM，畫面給別人看也安全。</li>
<li><b>答案優先，失敗時回到原文。</b>先立刻顯示原文，再請 LLM 整理答案；失敗、逾時或達用量上限時，直接展開原文。</li>
<li><b>沒把握就說「可能沒有答案」。</b>最高相似度低於門檻就提示，並且不呼叫 LLM，不亂答。</li>
</ul>{_memory(data)}</section>
<section><h2>4. 我比較了 5 種找法</h2>{(_scores(data) + _eng(data, n_segments, n_companies)) if data else err}</section>
<section><h2>5. 兩個失敗案例</h2>{_cases(data) if data else err}</section>
<section><h2>6. 限制</h2><ul class=plain>
<li>{counts}</li>
<li>題目與語料同源，沒有獨立測試題。「可能沒有答案」的門檻用同一批題挑，分數可能偏樂觀。</li>
{gen_limit}
<li>資料只有 {n_segments} 段。</li>
</ul></section>""")

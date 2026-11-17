"""專案說明頁的 HTML。數字全部來自 about.load() 的輸出；純 HTML/CSS，不用圖表庫。"""
import statistics

from markupsafe import escape

from . import METHODS, memory, retrieval
from .ui import page

LABEL = {"bm25": "BM25（jieba 斷詞）", "bge-small-zh": "bge-small-zh", "bge-m3": "bge-m3", "e5-large": "multilingual-e5",
         "hybrid": "混合（BM25＋bge-m3）"}
HYBRID = LABEL["hybrid"]  # 「混合」當方法名稱時一律寫這個，讓人知道混的是哪兩個
PLAIN = {"bm25": "關鍵字比對", "bge-small-zh": "小型向量模型", "bge-m3": "大型向量模型", "e5-large": "另一個向量模型", "hybrid": "關鍵字加向量"}
SHORT = {"bm25": "BM25", "bge-small-zh": "bge-small-zh", "bge-m3": "bge-m3", "e5-large": "e5", "hybrid": HYBRID}

def _f(x):
    return f"{x:.3f}"


def _where(gold):
    more = f"（另有 {len(gold) - 1} 處）" if len(gold) > 1 else ""
    return f"{gold[0]['file']} · {gold[0]['heading']}{more}"


def _rank(r, depth):
    return f"第 {r} 名" if r else f"前 {depth} 名內沒有"


def _gate_t(gt) -> str:
    """未指定公司的門檻；有已指定公司的題時，一併寫出較低的那個。"""
    return f"{gt['threshold']:.3f}" + (f"（已指定公司 {gt['scoped_threshold']:.3f}）" if gt.get("scoped_threshold") and gt.get("n_scoped") else "")


GEN_NOTE = "RAGAS 與 GPT 複查都於 2026-11-17～18 在補完職稱清單的語料、K=5 設定重跑（GPT 單次輸出有隨機性）。"


def _e2e(d) -> str:
    """「擋住 a/b」旁的脈絡：檢索門檻單獨擋得少，加上答案層後端到端的拒答數。缺檔就不加。"""
    x = d and d.get("e2e")
    return f"（再加答案層，端到端 {x['refused']}/{x['n']} 拒答）" if x else ""


def _held_p(d) -> str:
    return f"<p><b>獨立測試題</b>：{escape(_held_line(d))}。由單一模型出題、金標未經人工確認，只能當方向。</p>" if _held_line(d) else ""


def _held_types(x) -> str:
    """分題型與跨公司的一小段（輸出檔沒有就空）。職缺清單題、跨公司題各自的表現不混進總平均。"""
    bt = x.get("by_type") or {}
    t = "；".join(f"{k} {v['n']} 題 Hit@3 {_f(v['hit@3'])}、MRR {_f(v['mrr'])}" for k, v in bt.items())
    c = f"跨公司題 {x['cross_pass']}/{x['cross_n']} 通過關鍵字檢查" if x.get("cross_n") else ""
    return f"（分題型：{'；'.join(i for i in (t, c) if i)}）" if (t or c) else ""


def _held_line(d) -> str:
    """一句獨立測試題成績（票 39）；沒有輸出檔回空字串，呼叫端就維持原句。"""
    x = d and d.get("held")
    if not x:
        return ""
    e = f"、端到端拒答 {x['e2e']['refused']}/{x['e2e']['n']}" if x["e2e"] else ""
    return (f"另有 {x['n']} 題獨立測試題（沒用來調參）：Hit@3 ＝ {_f(x['hit3'])}（95% 區間 {_f(x['hit3_ci'][0])}–{_f(x['hit3_ci'][1])}）、"
            f"MRR ＝ {_f(x['mrr'])}（95% 區間 {_f(x['mrr_ci'][0])}–{_f(x['mrr_ci'][1])}）（Hit@3 與 MRR 只算 {x['n_plain_answerable']} 題單一公司與職缺清單的有答案題）{_held_types(x)}、"
            f"沒答案題檢索擋住 {x['blocked_u']}/{x['n_unanswerable']}{e}")


def _sweep_line(d) -> str:
    """一句切段掃描結果（票 40）；沒有輸出檔回空字串。數字與結論都直接取自輸出檔。"""
    x = d and d.get("sweep")
    if not x:
        return ""
    lens = sorted(x["hit3"])
    vals = "／".join(f"{x['hit3'][n]:.3f}" for n in lens)
    return f"掃過 {'／'.join(map(str, lens))} 字：Hit@3（三組題合併、{x['n']} 題單一公司有答案題）依序為 {vals}，結論：{x['conclusion']}"


def _real_line(d) -> str:
    x = d.get("real_eval")
    if not x:
        return _held_p(d)
    return _held_p(d) + (f"<p><b>另外 {x['n']} 道真實問法</b>（公司頁內短問句、單一公司、跨公司、語料沒有答案；同一人出題，題少，只能當方向）："
            f"非跨公司的有答案題 Hit@1 {_f(x['hit1'])}、Hit@3 {_f(x['hit3'])}、Hit@5 {_f(x['hit5'])}、MRR {_f(x['mrr'])}；"
            f"非跨公司的沒有答案題擋住 {x['blocked_u']}/{x['n_unanswerable']}{_e2e(d)}，有答案題誤擋 {x['blocked_a']}/{x['n_answerable']}；"
            f"跨公司題 {x['cross_passed']}/{x['cross_n']} 通過關鍵字檢查。</p>")


def _details(d) -> str:
    """詳細數字（預設收合）：完整成績表、查無門檻、生成層。名詞在這裡才出現，各解釋一次。"""
    rows = "".join(
        f"<tr><td>{escape(LABEL[r['method']])}</td>" + "".join(
            f"<td>{_f(r[k])}<small>[{_f(r['ci'][k][0])}, {_f(r['ci'][k][1])}]</small></td>" for k in ("hit@1", "hit@3", "mrr"))
        + "</tr>" for r in d["table"])
    g, c, gt = d["generation"], d["cross"], d["gate"]
    m3 = next(r for r in d["table"] if r["method"] == "bge-m3")
    intro = (
        f"<p>評分單位是段落。<b>Hit@3</b>：正確答案的那段，有排進前 3 名的題數比例（<b>Hit@1</b> 是第 1 名、<b>Hit@5</b> 是前 5 名）；"
        f"例：{d['n_answerable']} 題裡有 {m3['found']} 題前 3 名找到，Hit@3＝{_f(m3['hit@3'])}。"
        f"<b>MRR</b>（平均倒數名次）：正確段落平均排第幾名的倒數，越接近 1 越好。方括號是 95% 信賴區間："
        f"把 {d['n_answerable']} 題重抽 {d['bootstrap']} 次，成績落在這個範圍。名次最多看到第 {d['depth']}。</p>"
        f"<table><tr><th>找法</th><th>Hit@1</th><th>Hit@3</th><th>MRR</th></tr>{rows}</table>")
    gate = (f"<p><b>查無門檻</b>（bge-m3 最高相似度 {_gate_t(gt)}，低於它就提示「可能沒有答案」）："
            f"不可回答題擋住 {gt['unanswerable_blocked']}/{gt['n_unanswerable']}{_e2e(d)}，"
            f"可回答題誤擋 {gt['answerable_blocked']}/{gt['n_answerable']}。</p>")
    if g is None:  # 公開版：沒有 DeepSeek 金鑰，沒有生成層輸出
        return intro + "<p><b>生成層（RAGAS）</b>：這份輸出沒有生成層評估（需要 DeepSeek 金鑰，見 README）。</p>" + gate + _real_line(d)
    same = "同樣" if c["n"] == g["scored"] else "其中"
    verdict = "結果一致" if c["consistent"] else "結果和 RAGAS 不一致，請看輸出檔"
    failed = f"，評估失敗 {g['failed']} 題" if g["failed"] else ""
    return (
        intro +
        f"<p><b>生成層（RAGAS，用 LLM 當評審的 RAG 評估工具）</b>：忠實度（答案的每個陳述，段落裡找不找得到依據）平均 {_f(g['faithfulness'])}，"
        f"答案相關性（從答案反推問題，和原問題像不像）平均 {_f(g['answer_relevancy'])}。"
        f"已評分 {g['scored']} 題；另有 {g['gated']} 題被查無門檻擋住，沒有打分{failed}。{GEN_NOTE}</p>"
        + (f"<p>{_held_gen(d)}</p>" if _held_gen(d) else "") +
        f"<p>另請 GPT 獨立複查{same} {c['n']} 題（不是 RAGAS）：{c['claims']} 個陳述中 {c['supported']} 個有依據，"
        f"忠實度平均 {_f(c['mean'])}，{verdict}。{_held_cross(d)}</p>" + gate + _real_line(d))


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


def _mrr(d) -> str:
    """MRR 用條列白話說明，直接顯示在成績下面，不收合。數字取自輸出檔。"""
    best = next(r for r in d["table"] if r["method"] == "bge-m3")
    lo, hi = best["ci"]["mrr"]
    return ("<h3>MRR（平均倒數名次）</h3><ul class=plain>"
            "<li><b>量什麼：</b>正確段落排得多前面。</li>"
            f"<li><b>怎麼算：</b>每題取「1 ÷ 名次」（第 1 名 1 分、第 2 名 0.5 分、第 3 名約 0.33 分、前 {d['depth']} 名內沒有 0 分），再把所有題目平均。</li>"
            "<li><b>怎麼看：</b>越接近 1 越好。</li>"
            f"<li><b>我們的結果：</b>網站用的 bge-m3 是 {_f(best['mrr'])}（95% 區間 {_f(lo)}–{_f(hi)}）。</li></ul>")


def _held_gen(d) -> str:
    """獨立題（現行設定）的 RAGAS 一句話；輸出檔缺就回空字串。"""
    h = d.get("held_gen")
    if not h:
        return ""
    ar = f"，答案相關性 {_f(h['answer_relevancy'])}（{h['n_ar']} 題）" if h["answer_relevancy"] is not None else ""
    return (f"獨立題（現行設定：K=5、補公司名）：忠實度 {_f(h['faithfulness'])}（{h['n']} 題）{ar}；另有 {h['gated']} 題被查無門檻擋住、"
            f"{h['not_found']} 題生成回查無，沒有打分。同為 DeepSeek 評自己的答案，可能偏樂觀。")


def _held_cross(d) -> str:
    """獨立題的 GPT 複查一句；輸出檔缺就回空字串。"""
    h = d.get("held_cross")
    return f"獨立題另複查 {h['n']} 題：{h['claims']} 個陳述中 {h['supported']} 個有依據。" if h else ""


def _ragas(d) -> str:
    g = d["generation"]
    if g is None:
        return "<h3>RAGAS</h3><ul class=plain><li>用另一個語言模型當評審、替答案打分的評估工具。這份輸出沒有生成層評估（需要 DeepSeek 金鑰，見 README）。</li></ul>"
    return ("<h3>RAGAS</h3><ul class=plain>"
            "<li><b>量什麼：</b>答案好不好（不是段落找得準不準）。是用另一個語言模型當評審的開源評估工具。</li>"
            f"<li><b>忠實度 {_f(g['faithfulness'])}：</b>答案的每個說法，在給它的段落裡找得到依據。</li>"
            f"<li><b>答案相關性 {_f(g['answer_relevancy'])}：</b>答案有回答到問題。</li>"
            f"<li><b>範圍：</b>共評分 {g['scored']} 題。評審和生成同為 DeepSeek，可能偏愛自己的答案，所以另請 GPT 複查。</li>"
            f"<li><b>設定：</b>{GEN_NOTE}</li>" + (f"<li>{_held_gen(d)}</li>" if _held_gen(d) else "") + "</ul>")


def _level(d) -> str:
    """「RAG 程度一眼看」：做了什麼、刻意沒做什麼。數字取自輸出檔與程式常數；沒做的項目是專案實際沒有的功能。"""
    if not d:
        return ""
    best = next(r for r in d["table"] if r["method"] == "bge-m3")
    lo, hi = best["ci"]["mrr"]
    g, c = d["generation"], d["cross"]
    done = [
        "依標題切段，答案附出處與引用編號",
        f"比較 {len(METHODS)} 種找法（關鍵字、向量、{HYBRID}），用同一批題目量",
        f"檢索評估：MRR {_f(best['mrr'])}（95% 區間 {_f(lo)}–{_f(hi)}）",
        f"沒把握就不亂答：最高相似度低於 {retrieval.NOT_FOUND_THRESHOLD:.3f} 不呼叫 LLM",
    ]
    if g:
        done.append(f"答案評估：RAGAS 忠實度 {_f(g['faithfulness'])}、答案相關性 {_f(g['answer_relevancy'])}")
    if c:
        done.append(f"換一個 AI 獨立複查：{c['claims']} 個說法中 {c['supported']} 個有依據")
    if x := d.get("cross_eval"):
        done.append(f"跨公司提問：每家公司各找 {x['per']} 段再逐家整理；{x['n']} 題中 {x['passed']} 題通過關鍵字檢查（各家涵蓋率平均 {x['coverage']:.2f}）")
    done.append(f"追問記憶：帶入最近 {memory.MAX_TURNS} 輪（簡單規則）")
    undone = ["重排序模型（reranker）", "向量資料庫（資料只有數百段，在記憶體內搜尋就夠）", "微調模型",
              "線上監控與使用者回饋"] + ([] if d.get("held") else ["獨立測試題（題目與語料同源）"])

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
            ("查無門檻", f"最高相似度低於 {r.NOT_FOUND_THRESHOLD:.3f}（已指定公司 {r.NOT_FOUND_THRESHOLD - r.SCOPED_DROP:.3f}）：不呼叫 LLM"),
            ("生成", "DeepSeek，只根據段落回答"),
            ("答案與出處", "附引用編號；失敗回到原文")]
    ev = [("評估集", "手寫題目與金標段落"), ("MRR／Hit@k", "量找法"), ("RAGAS", "量答案"), ("另一個 AI 複查", "GPT 獨立複查")]
    mode = [("展示", "預設；只有公開事實段落"), ("自用", "本人密碼通過後才開；另有本機資料")]
    return (f"<div class=arch><p class=lab>主流程</p>{chain(main)}<p class=lab>評估迴路</p>{chain(ev)}"
            f"<p class=lab>模式隔離</p>{chain(mode)}</div>")


BINS = 6  # 直方圖格數；每格寬度由切塊上限算出，最後一格開放（>= 上限的都放進去）


def hist(lengths) -> list[tuple[str, int]]:
    """(區間標籤, 段數)。每個長度恰好落在一格，所以段數總和等於 len(lengths)。"""
    w = retrieval.CHUNK // BINS
    counts = [0] * BINS
    for n in lengths:
        counts[min(max(n - 1, 0) // w, BINS - 1)] += 1
    labels = [f"{i * w + 1}–{(i + 1) * w} 字" for i in range(BINS - 1)] + [f"{(BINS - 1) * w + 1} 字以上"]
    return list(zip(labels, counts))


def _lengths(lengths) -> str:
    """切段長度分佈：文字條直方圖＋統計。字數是 len(text)，和切塊常數同口徑。"""
    if not lengths:
        return ""
    bins = hist(lengths)
    top = max(n for _, n in bins) or 1
    bars = "<ul class=bars>" + "".join(
        f"<li><span class=lab>{escape(lab)}</span><span class=track><i style='width:{100 * n / top:.1f}%'></i></span><b>{n}</b></li>"
        for lab, n in bins) + "</ul>"
    return (f"<h3>切段長度</h3><p>共 {len(lengths)} 段；平均 {statistics.mean(lengths):.0f} 字、中位數 {statistics.median(lengths):.0f} 字、"
            f"最長 {max(lengths)} 字（字數不含前面加的公司名與標題）。每格是落在該長度的段數。</p>{bars}"
            f"<p>切塊常數：太長的段落再切成約 {retrieval.CHUNK} 字、重疊 {retrieval.OVERLAP} 字。"
            "為什麼先依標題切：一個標題底下通常就是一個主題（例如「職缺」「技術堆疊」），整段一起找，答案不會被切在兩半；只有太長的才再切。</p>")


def _ci(r) -> str:
    return f"{_f(r['mrr'])}（95% 區間 {_f(r['ci']['mrr'][0])}–{_f(r['ci']['mrr'][1])}）"


def _trade(d, n_segments: int) -> str:
    """取捨表：一列一個決定。數字取自輸出檔與載入結果；沒有紀錄的數字不寫（reranker 沒量過就直說）。"""
    by = {r["method"]: r for r in d["table"]}
    m3, sm, e5 = by["bge-m3"], by["bge-small-zh"], by["e5-large"]
    overlap = all(m3["ci"]["mrr"][0] <= r["ci"]["mrr"][1] for r in (sm, e5))
    perf = d["perf"]
    speed = (f"bge-m3 載入約 {perf['load']} 秒、預熱後單次查詢中位數約 {perf['query']} 秒（本機模擬，不是雲端實測，見 eval/spaces_feasibility.md）；"
             if perf else "")
    df = d["mrr_diff"]
    gen = d["cross"]
    check = f"GPT 複查 {gen['claims']} 個說法中 {gen['supported']} 個有依據；" if gen else ""
    rows = [
        ("選 FAISS，不選 Qdrant／Milvus",
         f"資料只有 {n_segments} 段，在記憶體內搜尋就夠，不必另外架一個資料庫服務。資料大很多時再換（見下方放大 100 倍）。"),
        ("選 bge-m3，不選 bge-small-zh／multilingual-e5",
         f"MRR：bge-m3 {_ci(m3)}，bge-small-zh {_ci(sm)}，multilingual-e5 {_ci(e5)}。"
         + ("區間有重疊，差距只能當方向。" if overlap else "") + speed + "bge-small-zh 與 e5 沒量過載入與編碼時間。"),
        ("不加重排序模型（reranker）",
         f"沒量過。資料少，單獨 bge-m3 的 MRR 已有 {_f(m3['mrr'])}；沒有試過加 reranker 會不會更好。"),
        ("不用混合檢索（BM25＋bge-m3）",
         f"{HYBRID}＝BM25 關鍵字名次加 bge-m3 語意名次，用 RRF 合併。原本預期它會贏。bge-m3 減{HYBRID}的 MRR 差 {df['diff']:+.3f}，95% 區間 [{df['lo']:+.3f}, {df['hi']:+.3f}]"
         + ("：區間含 0，數據沒有支持混合比較好，所以用較簡單的單一向量找法。" if df["lo"] <= 0 <= df["hi"]
            else f"：區間不含 0，單一向量找法與{HYBRID}的差異可信。")),
        ("DeepSeek 生成與評審，另請 GPT 複查",
         f"{check}評審和生成同為 DeepSeek，可能偏愛自己的答案，所以另請 GPT 複查；兩者都只量答案有沒有依據，不量對不對。"
         if gen else "評審和生成同為 DeepSeek，可能偏愛自己的答案；兩者都只量答案有沒有依據，不量對不對。這份輸出沒有複查結果。"),
    ]
    return ("<h3>為什麼選這個，不選那個</h3><ul class=trade>"
            + "".join(f"<li><b>{escape(t)}</b><span>{escape(x)}</span></li>" for t, x in rows) + "</ul>")


def _scale() -> str:
    """設計說明，不是已實作：寫死的文字，頁面明確標示。"""
    items = ["向量庫換成近似最近鄰索引（例如 HNSW），並支援增量索引：新增資料只編碼新段落。",
             "解析管線：支援 PDF，掃描檔加 OCR，再進現有的切段。",
             "快取與成本控制：相同問題的答案快取，LLM 用量按使用者計量。",
             "權限與多使用者：帳號、角色，取代單一存取碼。",
             "評估集擴充與持續回歸：題目增加後每次改動自動重跑，成績掉了就擋下。",
             "觀測與追蹤：記錄每次查詢的找到段落、延遲與失敗原因。"]
    return ("<h3>資料放大 100 倍會怎麼改</h3><p class=note><b>設計說明，不是已實作。</b>下面每一項目前都沒有做。</p><ul class=plain>"
            + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>")


def _limits(d) -> str:
    items = ["單機：一台電腦、一個行程。", "存取碼與本人密碼是唯一的權限控管。",
             f"題少：只有 {d['n_answerable']} 題有答案、{d['n_unanswerable']} 題沒答案。", (_held_line(d) + "。其餘題目與語料同源。") if _held_line(d) else "沒有獨立測試題：題目與語料同源。"]
    if x := d.get("cross_eval"):
        items.append(f"跨公司題的查無常數 {x['floor']} 用同一批 {x['n']} 題挑的，偏樂觀；可回答題有 {x['n_answerable'] - x['answerable_ok']} 題被誤擋。")
    return "<h3>目前限制</h3><ul class=plain>" + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>"


def _eng(d, n_segments: int, n_companies: int, lengths=None) -> str:
    """給工程師讀者的技術細節（預設收合）。附在第 4 塊底下；沒有評估資料時整塊不顯示。"""
    return (f"<details class=eng><summary>給{retrieval.ENG_AUDIENCE}：技術細節</summary>"
            f"<h3>系統架構</h3>{_arch(n_segments, n_companies)}{_lengths(lengths)}"
            f"{_trade(d, n_segments)}{_scale()}{_limits(d)}</details>")


def _fixes(d) -> str:
    """三次用數據做的修正：每項一行「之前 → 之後」。只放有檔案可對照的；缺檔的那一項不顯示。"""
    by = {r["method"]: r for r in d["table"]}
    df, rf = d["mrr_diff"], d["ragas_fix"]
    items = [
        f"<b>找法：</b>BM25 的 MRR {_ci(by['bm25'])} → bge-m3 的 MRR {_ci(by['bge-m3'])}。",
        f"<b>混合檢索（BM25＋bge-m3）被否決：</b>我們原本預期{HYBRID}會贏，數據沒有支持。bge-m3 減{HYBRID}的 MRR 差 {df['diff']:+.3f}，"
        f"95% 區間 [{df['lo']:+.3f}, {df['hi']:+.3f}]"
        + ("，含 0，看不出混合比較好。" if df["lo"] <= 0 <= df["hi"] else "，不含 0。"),
    ]
    if rf:
        items.append(f"<b>評估程式的錯誤：</b>第一次 RAGAS 忠實度 {_f(rf['first'])}（評分 {rf['first_scored']} 題，舊題組；原因是評審沒看到公司名）"
                     f" → 修正後 {_f(rf['now'])}（評分 {rf['now_scored']} 題）。題組與評分題數不同，只能看方向。")
    if d["live_test"]:
        items.append("<b>提示詞修正：</b>不再把「某某頁面」寫成公司已採用。後續連線測試仍抓到其他類型的錯誤（見 eval/live_test.md）。")
    return "<h3>三次用數據做的修正</h3><ul class=plain>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def _find(d) -> str:
    """第 3 段的證據：找法成績。單公司與跨公司取幾段都讀程式常數。"""
    return (f"<p>用 {d['n_answerable']} 道有答案的題目，量五種找法：正確的段落有沒有排進前 3 名。條越長越好。</p>"
            f"{_bars(d)}<p>問單一公司：取前 {retrieval.DEFAULT_K} 段。問「全部公司」：每家公司各取 {retrieval.PER_COMPANY} 段。</p>"
            f"{_mrr(d)}<details class=more><summary>看詳細數字</summary>{_details(d)}</details>")


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


def _library(n_segments: int) -> str:
    """放大 100 倍，用圖書館比喻。內容與 _scale 同一份設計說明，不是已實作。"""
    items = [f"現在像一個小書架：{n_segments} 段，直接翻就找得到。",
             "放大 100 倍像變成一棟圖書館：要換成更快的目錄（近似搜尋的索引），新書只登記新書，不重編全部。",
             "書的格式變多（PDF、掃描檔）：要先把書轉成文字，再切段。",
             "來借書的人變多：要有借書證與管理員（帳號與權限），還要有借書紀錄（記錄每次查詢）。",
             "題目要更多，每次改完自動重考；成績掉了就擋下。"]
    return ("<h3>放大 100 倍，像圖書館變大</h3><p class=note><b>設計說明，不是已實作。</b>下面每一項目前都沒有做。</p><ul class=plain>"
            + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>")


def _decisions(*items) -> str:
    return "<ul class=plain>" + "".join(f"<li><b>{escape(t)}</b>{escape(x)}</li>" for t, x in items) + "</ul>"


def _say(lines) -> str:
    """③ 講稿：口語、短句；預設收合，給人看畫面時不搶眼。None 的句子（缺資料）直接略過。"""
    return ("<details class=say><summary>講稿：這樣說</summary><ul class=plain>"
            + "".join(f"<li>{escape(x)}</li>" for x in lines if x) + "</ul></details>")


def _seg(n, title, claim, evidence, say) -> str:
    """一段固定三塊：① 一句話主張（大字）② 證據 ③ 講稿。"""
    return (f"<section id=s{n} class=seg><h2>{n}. {escape(title)} <span class=t>約 30 秒</span></h2>"
            f"<p class=claim>{escape(claim)}</p>{evidence}{_say(say)}</section>")


def _vs_line(d) -> str:
    v = next((x for x in d["versus"] if x["method"] == "hybrid"), None) if d else None
    return f"{v['n']} 題裡 {v['tie']} 題排名一樣、{v['win']} 題 bge-m3 排得比較前、{v['loss']} 題比較後；" if v else ""


def _qa(d, n_segments: int) -> str:
    """問答備案：常被追問的 5 題。數字取自輸出檔與載入結果；缺資料的句子略過。"""
    m3 = next((r for r in d["table"] if r["method"] == "bge-m3"), None) if d else None
    df, gt = (d["mrr_diff"], d["gate"]) if d else (None, None)
    rows = [
        ("資料放大 100 倍怎麼辦？",
         ["我沒做過大規模，不能說已經解決。", f"現在只有 {n_segments} 段，在記憶體裡找就夠。",
          "變多了要換索引、做增量更新，再重新評估。"]),
        ("為什麼不用重排序模型（reranker）？",
         ["我沒有試過。", f"資料少，bge-m3 的 MRR 已有 {_f(m3['mrr'])}。" if m3 else None,
          "加了會不會更好，我沒量過，所以不說它有用或沒用。"]),
        ("為什麼混合檢索（BM25＋bge-m3）沒有贏？",
         [f"我原本以為{HYBRID}會贏。",
          (_vs_line(d) + f"MRR 差 {df['diff']:+.3f}，95% 區間 [{df['lo']:+.3f}, {df['hi']:+.3f}]。") if df else None,
          ("區間含 0，看不出誰比較好。所以我用比較簡單的單一向量找法。" if df and df["lo"] <= 0 <= df["hi"]
           else "區間不含 0，兩者的差異可信。" if df else None)]),
        ("查無門檻是不是太樂觀？",
         ["是，偏樂觀。門檻是用同一批題目挑的，新題目不保證一樣。",
          (f"不可回答題擋住 {gt['unanswerable_blocked']}/{gt['n_unanswerable']}{_e2e(d)}，可回答題誤擋 {gt['answerable_blocked']}/{gt['n_answerable']}。" if gt else None)]),
        ("沒有向量資料庫，算向量檢索嗎？",
         ["算。我把問題和每一段都轉成向量，比相似度，這就是向量檢索。",
          "我用 FAISS 在記憶體裡比，不另外架資料庫服務。", f"資料只有 {n_segments} 段，這樣就夠。"]),
    ]
    body = "".join(f"<details><summary>{escape(q)}</summary><p>{escape(''.join(x for x in a if x))}</p></details>" for q, a in rows)
    return ("<section id=qa class=seg><h2 class=qa>問答備案 <span class=t>被追問時看</span></h2>"
            f"<p class=claim>常被追問的 5 題，照實回答。</p><div class=qalist>{body}</div></section>")


def _speech(d, n_companies: int, n_segments: int) -> dict:
    """各段講稿。口語、白話、一句一個重點；有數字的句子取自輸出檔與程式常數，沒資料就略過。"""
    r = retrieval
    by = {t["method"]: t for t in d["table"]} if d else {}
    m3 = by.get("bge-m3")
    g, c, gt, df, x = (d["generation"], d["cross"], d["gate"], d["mrr_diff"], d.get("cross_eval")) if d else (None,) * 5
    n = d["n_answerable"] if d else None
    top_mrr = d and max(d["table"], key=lambda t: t["mrr"])["method"] == "bge-m3"
    fix = d and d["ragas_fix"]
    return {
        1: ["這是我做的求職資料問答。", "現場有很多家公司，我想快速查它們做什麼、有什麼職缺。",
            "點一家公司就能問，答案會附出處。", "它準不準，我用題目量過，後面會講。"],
        2: ["資料來自我做的公司調查筆記。", "我只留公開查得到的事實，像公司做什麼、職缺、技術、財務。",
            "個人意見與推測，載入時就丟掉。不進索引，也不會送給語言模型。",
            f"一共 {n_companies} 家公司、{n_segments} 段。", "每段前面加公司名，問到公司時比較容易對上。"],
        3: ["我先問：哪種找法最會找？",
            f"我手寫了 {n} 道有答案的題目，比了 {len(METHODS)} 種找法。" if d else None,
            "看正確的段落有沒有排進前 3 名，這叫 Hit@3；排第 1 名是 Hit@1，前 5 名是 Hit@5。",
            f"網站用的 {r.DEFAULT_METHOD}，{m3['found']} / {n} 題排進前 3 名。" if m3 else None,
            "MRR 的意思是：正確段落排第 1 名得 1 分，第 2 名得 0.5 分，再全部平均。越接近 1 越好。" if d else None,
            (f"bge-m3 的 MRR 是 {_f(m3['mrr'])}" + ("，是五種裡最高的。" if top_mrr else "。")) if m3 else None,
            f"我原本以為{HYBRID}會更好。數據看不出來，所以選比較簡單的 bge-m3。" if df and df["lo"] <= 0 <= df["hi"] else None,
            f"問單一公司取前 {r.DEFAULT_K} 段；問全部公司，每家取 {r.PER_COMPANY} 段。"],
        4: ["找得到還不夠，答案也要有依據。",
            f"我用 RAGAS 打分。忠實度 {_f(g['faithfulness'])}：答案的每個說法，在原文裡找得到依據。這是 2026-11-17～18 在補完職稱清單的語料、取前 5 段重跑的結果。" if g else None,
            "但評審和生成都是 DeepSeek，可能偏愛自己的答案。" if g else None,
            f"所以另請 GPT 複查：{c['claims']} 個說法裡，{c['supported']} 個有依據。" if c else None,
            "這只量有沒有依據，不量對不對。" if g else None,
            f"沒把握時，系統不亂答。最高相似度低於 {r.NOT_FOUND_THRESHOLD:.3f}（已指定公司 {r.NOT_FOUND_THRESHOLD - r.SCOPED_DROP:.3f}），就說「可能沒有答案」。",
            (f"故意問沒有答案的 {gt['n_unanswerable']} 題，擋住 {gt['unanswerable_blocked']} 題{_e2e(d)}。"
             f"代價是有答案的 {gt['n_answerable']} 題，誤擋 {gt['answerable_blocked']} 題。" if gt else None),
            "門檻用同一批題目挑，偏樂觀。門檻高低怎麼影響結果，可以到「查無門檻」頁自己拖拖看。"],
        5: ["做的過程，我踩到幾個坑。",
            f"第一，換找法：BM25 的 MRR {_f(by['bm25']['mrr'])}，換成 bge-m3 是 {_f(m3['mrr'])}。" if m3 else None,
            f"第二，混合檢索（BM25＋bge-m3）被否決。原本預期它會贏，數據沒有支持。" if df and df["lo"] <= 0 <= df["hi"] else None,
            (f"第三，評估程式自己有錯：評審沒看到公司名，第一次忠實度 {_f(fix['first'])}，修正後 {_f(fix['now'])}。題組不同，只能看方向。" if fix else None),
            "連線實測還抓到：答案把「某某頁面」寫成公司採用。我改了提示詞，但仍抓到別的錯誤。" if d and d["live_test"] else None,
            "下面兩個失敗案例，是程式從輸出檔自動挑的，不是我挑好看的。" if d else None],
        6: ["最後講限制。我不想講得太滿。",
            f"題目只有 {d['n_answerable']} 題有答案、{d['n_unanswerable']} 題沒答案，只能當方向。" if d else "題目很少，只能當方向。",
            (_held_line(d) + "。其餘題目與資料同源。") if _held_line(d) else "題目和資料同源，沒有獨立測試題。",
            f"跨公司題 {x['n']} 題中 {x['passed']} 題通過關鍵字檢查。但它的門檻也用同一批題挑，偏樂觀。" if x else None,
            "我刻意沒做：重排序模型、向量資料庫、微調模型、線上監控。沒做就是沒做。",
            "放大 100 倍會怎麼改，只是設計想法，我還沒有做。"],
    }


ABOUT_CSS = """.order{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;margin:0 0 20px;color:var(--mute);font-size:.9375rem}
.order ol{display:flex;flex-wrap:wrap;gap:4px;list-style:none;padding:0;margin:0}.order li{margin:0;display:flex;align-items:center}
.order li:not(:last-child)::after{content:"\\2192";margin-left:4px;color:var(--mute)}
.order a{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:48px;padding:0 8px;font-weight:650;text-decoration:none;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.order button{min-height:48px;padding:0 16px;color:var(--acc);border-color:var(--acc);font-weight:600}
[hidden]{display:none!important}
h2 .t{font-size:.8125rem;font-weight:400;color:var(--mute);white-space:nowrap;margin-left:6px}
.claim{font-size:1.5rem;line-height:1.45;font-weight:650;margin:0 0 16px}
.say{margin-top:20px;background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:0 14px;color:var(--mute)}
.say .plain li{margin:8px 0}
.qalist details{border-top:1px solid var(--line)}.qalist summary{min-height:56px}.qalist p{margin:0 0 12px}
#pmbar{display:none}
.pm .order,.pm h1,.pm nav,.pm footer,.pm .seg:not(.cur){display:none}
.pm .seg{padding-bottom:96px}.pm h2{margin-top:12px}.pm .claim{font-size:1.75rem}
.pm #pmbar{display:flex;gap:8px;position:fixed;left:0;right:0;bottom:0;max-width:820px;margin:0 auto;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:var(--bg);border-top:1px solid var(--line)}
#pmbar button{flex:1;min-height:56px;font-size:1.0625rem;padding:0 6px}#pmbar .pos{min-width:56px;display:flex;align-items:center;justify-content:center;color:var(--mute);font-variant-numeric:tabular-nums}
#pmnext{background:var(--acc);border-color:var(--acc);color:var(--on-acc);font-weight:600}
button:disabled{opacity:.4;cursor:default}"""

# 簡報模式：一次顯示一段。上一步／下一步與左右鍵；網址加 #pm 直接進入。沒有 JS 時按鈕不出現，整頁照常捲動。
ABOUT_JS = """<script>(function(){var b=document.body,S=[].slice.call(document.querySelectorAll('.seg')),i=0,on=false,
$=function(x){return document.getElementById(x)},pos=$('pmpos'),pv=$('pmprev'),nx=$('pmnext');
function show(n){i=Math.max(0,Math.min(S.length-1,n));S.forEach(function(s,k){s.classList.toggle('cur',k===i)});
pos.textContent=(i+1)+' / '+S.length;pv.disabled=i===0;nx.disabled=i===S.length-1;window.scrollTo(0,0)}
function go(o){on=o;b.classList.toggle('pm',o);if(o)show(0)}
$('pmbtn').hidden=false;$('pmbtn').onclick=function(){go(true)};$('pmx').onclick=function(){go(false)};
pv.onclick=function(){show(i-1)};nx.onclick=function(){show(i+1)};
document.addEventListener('keydown',function(e){if(!on||e.altKey||e.ctrlKey||e.metaKey)return;
if(e.key==='ArrowRight')show(i+1);else if(e.key==='ArrowLeft')show(i-1);else if(e.key==='Escape')go(false)});
if(location.hash==='#pm')go(true)})();</script>"""


def render(data: dict | None, error: str, n_segments: int, n_companies: int, lengths=None) -> str:
    """data 為 None 時（輸出檔缺或過期），成績與失敗案例改顯示明確錯誤，不用舊數字。
    順序是現場講解的順序：這是什麼 → 資料 → 找法 → 怎麼確認 → 踩到的坑 → 限制，最後是問答備案。"""
    err = f"<p class=err>無法顯示：{escape(error)}</p>"
    gen_limit = ("<li>評審與生成同為 DeepSeek，可能偏愛自己的答案。已另用 GPT 複查，但兩者都只量「答案有沒有依據」，不量對不對。</li>"
                 if not data or data["generation"] else "")
    counts = f"只有 {data['n_answerable']} 題有答案、{data['n_unanswerable']} 題沒答案，只能當方向。" if data else "題目很少，只能當方向。"
    say = _speech(data, n_companies, n_segments)
    gate = (f"<p><b>查無門檻</b>（最高相似度低於 {_gate_t(data['gate'])} 就提示「可能沒有答案」）："
            f"不可回答題擋住 {data['gate']['unanswerable_blocked']}/{data['gate']['n_unanswerable']}{_e2e(data)}，"
            f"可回答題誤擋 {data['gate']['answerable_blocked']}/{data['gate']['n_answerable']}。</p>") if data else ""
    s1 = _seg(1, "這是什麼", "點一家公司，直接問問題，答案附出處。",
              f"<p class=lead>答案先出現，附出處；原文收在下面，隨時可以核對。目前收 {n_companies} 家公司的公開資料。</p>"
              f"{_stats(data)}<h3>它怎麼運作</h3>{_flow(n_segments, n_companies)}", say[1])
    s2 = _seg(2, "資料與切段", "只收公開的事實，依標題切成段落。",
              f"<p>{n_companies} 家公司，共 {n_segments} 段公開事實段落。太長的段落再切成約 {retrieval.CHUNK} 字、重疊 {retrieval.OVERLAP} 字。{escape(_sweep_line(data))}</p>"
              + _decisions(("依標題切段，每段前面加公司名。", "這樣問句提到公司或主題時，比較容易對上。"),
                           ("只用公開事實。", "個人意見與推測在載入時就丟掉：不進索引、不送 LLM，畫面給別人看也安全。")), say[2])
    s3 = _seg(3, "怎麼找", f"我用同一批題目比了 {len(METHODS)} 種找法，網站用 {retrieval.DEFAULT_METHOD}。",
              _decisions(("比較五種找法。", "不先假設哪種好，用同一批題目量。")) + (_find(data) if data else err), say[3])
    s4 = _seg(4, "怎麼確認答對", "答案要有依據；沒把握就說「可能沒有答案」。",
              _decisions(("答案優先，失敗時回到原文。", "先立刻顯示原文，再請 LLM 整理答案；失敗、逾時或達用量上限時，直接展開原文。"),
                         ("沒把握就說「可能沒有答案」。", "最高相似度低於門檻就提示，並且不呼叫 LLM，不亂答。"))
              + ((gate + _ragas(data)) if data else err)
              + "<p class=link><a href=/threshold>查無門檻：自己拖拖看</a></p>", say[4])
    s5 = _seg(5, "踩到的坑與三次修正", "我踩到幾個坑，每次都用數據修，不憑感覺。",
              ((_fixes(data) + "<h3>兩個失敗案例</h3>" + _cases(data)) if data else err), say[5])
    s6 = _seg(6, "限制與下一步", "這是小規模的驗證，數字只能當方向。",
              f"<ul class=plain><li>{counts}</li>"
              + (f"<li>{escape(_held_line(data))}。其餘題目與語料同源，「可能沒有答案」的門檻用它們挑，分數可能偏樂觀。</li>" if _held_line(data) else "<li>題目與語料同源，沒有獨立測試題。「可能沒有答案」的門檻用同一批題挑，分數可能偏樂觀。</li>")
              + f"{gen_limit}<li>資料只有 {n_segments} 段。</li></ul>{_memory(data)}{_level(data)}{_library(n_segments)}"
              + (_eng(data, n_segments, n_companies, lengths) if data else ""), say[6])
    order = ("<div class=order><b>講解順序</b><ol>"
             + "".join(f"<li><a href=#s{i}>{i}</a></li>" for i in range(1, 7)) + "<li><a href=#qa>問答</a></li></ol>"
             "<button id=pmbtn type=button hidden>簡報模式</button></div>")
    bar = ("<div id=pmbar role=toolbar aria-label=簡報控制><button id=pmprev type=button>上一步</button><span class=pos id=pmpos aria-live=polite></span>"
           "<button id=pmnext type=button>下一步</button><button id=pmx type=button>離開</button></div>")
    return page("專案說明｜求職情報問答", f"""<nav><a href="/">問答</a><b>專案說明</b></nav>
<h1>求職情報問答</h1>{order}
{s1}
{s2}
{s3}
{s4}
{s5}
{s6}
{_qa(data, n_segments)}{bar}{ABOUT_JS}""", head=f"<style>{ABOUT_CSS}</style>")

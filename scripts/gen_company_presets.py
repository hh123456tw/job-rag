"""離線產生每家公司的預設題目（票 21）：python -X utf8 scripts/gen_company_presets.py

需要 JOB_RAG_CORPUS、JOB_RAG_MODELS（用真語料與真 bge-m3；向量快取在 JOB_RAG_CACHE）。不呼叫任何 LLM。
規則：候選題庫依固定優先序，每題對該公司用 search(gate=True) 檢查：
  1. 沒有被查無門檻擋住（結果不為空）；
  2. 第 1 名段落的標題路徑含該題的關鍵字之一（避免點了找不到）。
通過者依優先序取前 5 題。少於 3 題時，補到 3 題（先補沒被門檻擋住、但標題關鍵字沒對上的題，再補其餘），並標 thin，
對話框的打招呼訊息會加一句「這家公開資料較少，答案可能很短」。
「全部公司」：跨公司候選題，要求未被擋住、問句不含公司名（不被自動偵測成單一公司），且第 1 名段落的標題或內文含關鍵字
（題目要寫得貼近段落用語：「X 的職缺有哪些？」；實測問「哪些公司…」這類句型會被查無門檻擋住，門檻沒有調整）；取前 4 題。
輸出 job_rag/company_presets.json（只有題目文字，不含語料內容）。
"""
import json
from pathlib import Path

from job_rag import detect_company, retrieval, search

# (鍵, 按鈕文字, 接在公司名後的句尾, 第 1 名標題路徑要含的關鍵字之一)；順序即優先序
BANK = [
    ("what", "這家做什麼", "是做什麼的？", ("基本資料", "業務", "簡介", "產品", "公司")),
    ("jobs", "有哪些職缺", "有哪些職缺？", ("職缺",)),
    ("tech", "用什麼技術", "的技術堆疊與開發工具有哪些？", ("技術", "開發")),
    ("fin", "財務與新聞", "的營收和近期新聞是什麼？", ("財務", "營收", "新聞", "營運")),
    ("ai", "有 AI 嗎", "有沒有 AI 相關的產品或職缺？", ("AI", "產品", "職缺")),
    ("skills", "職缺要會什麼", "的職缺要會哪些技能？", ("職缺", "技能")),
    ("travel", "出差或外派", "的職缺需要出差或外派嗎？", ("職缺", "出差", "外派")),
    ("salary", "薪資範圍", "的職缺薪資範圍是多少？", ("職缺", "薪")),
]
# 跨公司題：(鍵, 按鈕文字, 問句, 第 1 名內文要含的關鍵字之一)
ALL_BANK = [
    ("py", "Python 後端職缺", "Python 後端工程師的職缺有哪些？", ("Python",)),
    ("fullstack", "Python 全端職缺", "Python 全端工程師的職缺有哪些？", ("Python", "全端")),
    ("cloud", "雲端職缺", "雲端工程師的職缺有哪些？", ("雲端",)),
    ("front", "前端職缺", "前端工程師的職缺有哪些？", ("前端",)),
    ("ai", "AI 平台職缺", "AI 平台架構師的職缺有哪些？", ("AI",)),
    ("java", "Java 職缺", "Java 工程師的職缺有哪些？", ("Java", "JAVA")),
]
# 票 31：跨公司預設題（走跨公司路徑）。要求被偵測為跨公司、最高分不低於 CROSS_FLOOR；放在「全部公司」的最前面。
# 「面試」題不放這裡：展示索引不收面試內容（自用模式的面經題另有 IV_ALL）；第三題改用出差或外派。
CROSS_BANK = [
    ("x_salary", "哪間薪水好", "哪一間薪水比較好？"),
    ("x_tech", "哪些用 Python", "哪些公司用 Python？"),
    ("x_travel", "哪家要出差", "哪一家的職缺需要出差或外派？"),
]


def ok_cross(q):
    if not retrieval.is_cross(q):
        return False
    hits = retrieval.cross_search(q, companies={n for _, n in __import__("app")._company_buttons()})
    return bool(hits) and max(h["score"] for h in hits) >= retrieval.CROSS_FLOOR


def ok_company(label, name, tail, kws):
    hits = search(f"{label}{tail}", company=name, gate=True, dedupe=True)
    return bool(hits) and any(k in hits[0]["heading_path"] for k in kws)


def ok_all(q, kws):
    if detect_company(q):
        return False
    hits = search(q, gate=True, dedupe=True)
    return bool(hits) and any(k in hits[0]["heading_path"] + hits[0]["text"] for k in kws)


def build():
    import app  # LIVE_COMPANIES；用 _company_buttons() 讓範例語料也能跑
    out = {"companies": {}, "all": []}
    for label, name in app._company_buttons():
        passed = [(k, b, f"{label}{t}") for k, b, t, kws in BANK if ok_company(label, name, t, kws)]
        thin = len(passed) < 3
        if thin:
            have = {k for k, _, _ in passed}
            rest = [(k, b, t) for k, b, t, _ in BANK if k not in have]
            gated_ok = [x for x in rest if search(f"{label}{x[2]}", company=name, gate=True, dedupe=True)]  # 先補沒被門檻擋住的
            fill = (gated_ok + [x for x in rest if x not in gated_ok])[: 3 - len(passed)]
            passed += [(k, b, f"{label}{t}") for k, b, t in fill]
        out["companies"][label] = {"thin": thin, "presets": [{"key": k, "label": b, "q": q} for k, b, q in passed[:5]]}
    out["all"] = ([{"key": k, "label": b, "q": q} for k, b, q in CROSS_BANK if ok_cross(q)]
                  + [{"key": k, "label": b, "q": q} for k, b, q, kws in ALL_BANK if ok_all(q, kws)][:2])
    return out


if __name__ == "__main__":
    data = build()
    path = Path(__file__).parent.parent / "job_rag" / "company_presets.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for label, c in data["companies"].items():
        print(label, len(c["presets"]), "補足" if c["thin"] else "", [p["key"] for p in c["presets"]])
    print("全部公司", [p["key"] for p in data["all"]], f"門檻 {retrieval.NOT_FOUND_THRESHOLD}")

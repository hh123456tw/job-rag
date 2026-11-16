"""量 4 個常用問題句型 x 現場公司（8 家，共 32 題；數字由程式算），寫出 eval/button_check.md。
python -X utf8 eval/button_check.py      （需要 JOB_RAG_CORPUS、JOB_RAG_MODELS；約 4 分鐘）
問句與介面相同：句型代入公司名，只搜該公司，去重開、不套門檻（gate=False）。
「第 1 名是否合理」是人看過段落標題與內容後寫的（RATINGS），不是程式判斷；「被擋住」＝第 1 名分數低於 NOT_FOUND_THRESHOLD。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import app as appmod  # noqa: E402
from job_rag import retrieval, search  # noqa: E402

KINDS = {"what": "這家做什麼", "jobs": "有哪些職缺", "tech": "用什麼技術", "fin": "財務與新聞"}
# 每個句型的候選句尾（第 1 個是原本的）
CANDIDATES = {
    "what": ["是做什麼的？", "的公司簡介是什麼？", "的主要業務和產品是什麼？", "的公司簡介與主要業務是什麼？", "的基本資料與業務是什麼？"],
    "jobs": ["有哪些職缺？", "目前有哪些開放職缺？", "的職缺有哪些？", "目前有哪些開放職缺與職務？", "有哪些開放職缺與所需技能？"],
    "tech": ["用什麼技術？", "的技術堆疊是什麼？", "使用哪些技術？", "技術堆疊", "的技術堆疊與開發工具有哪些？",
             "的技術堆疊有哪些？", "使用的技術堆疊與開發工具有哪些？"],
    "fin": ["的營收和近期新聞是什麼？", "的財務與新聞", "的營收與近期新聞", "的財務狀況和新聞是什麼？",
            "的近 3 年營收與近一年新聞是什麼？", "的營收、獲利與近一年新聞是什麼？"],
}
# 候選表的自動粗判：第 1 名的標題／檔名／前 160 字含這些字（只是粗略；原句型與選定句型另有人工判斷）
PROXY = {"what": r"基本資料|業務|簡介", "jobs": r"職缺|職稱|104|職務", "tech": r"技術堆疊", "fin": r"營收|財務|新聞|獲利"}

# 人工判斷：合理 / 不合理 / 不確定 ＋ 理由。依段落標題與內容。
Y, N, U = "合理", "不合理", "不確定"
RATINGS = {
    ("what", "是做什麼的？"): {
        "台灣大哥大": (U, "基本資料表，沒看到業務欄"), "聯合報": (Y, "商工登記，含營業項目"), "叡揚資訊": (U, "基本資料表，沒看到業務欄"),
        "神通資訊": (U, "基本資料表，沒看到業務欄"), "藍新資訊": (U, "基本資料表，沒看到業務欄"), "凱基證券": (Y, "業務：產品線"),
        "華電聯網": (U, "基本資料表，沒看到業務欄"), "中華網龍": (U, "基本資料，沒看到業務欄"),
        },
    ("jobs", "有哪些職缺？"): {
        "台灣大哥大": (Y, "單一職缺詳細，屬職缺"), "聯合報": (Y, "104 公司頁職缺"), "叡揚資訊": (Y, "其他列表職缺"),
        "神通資訊": (Y, "104 公司頁職缺"), "藍新資訊": (Y, "職缺表"), "凱基證券": (Y, "列表頁職缺"), "華電聯網": (Y, "104 公司頁職缺"),
        "中華網龍": (Y, "職缺表"), },
    ("tech", "用什麼技術？"): {
        "台灣大哥大": (Y, "技術堆疊"), "聯合報": (Y, "技術堆疊"), "叡揚資訊": (N, "基本資料；技術堆疊在別段"), "神通資訊": (N, "基本資料；技術堆疊在別段"),
        "藍新資訊": (N, "基本資料；技術堆疊在別段"), "凱基證券": (Y, "技術堆疊"), "華電聯網": (N, "基本資料；技術堆疊在別段"),
        "中華網龍": (Y, "技術堆疊"), },
    ("fin", "的營收和近期新聞是什麼？"): {
        "台灣大哥大": (Y, "業務與財務"), "聯合報": (U, "子公司商工登記，不是營收或新聞"), "叡揚資訊": (Y, "近一年新聞"), "神通資訊": (U, "基本資料表，財務欄不明"),
        "藍新資訊": (Y, "近一年新聞"), "凱基證券": (Y, "近一年新聞"), "華電聯網": (Y, "營收（核對結果）"), "中華網龍": (Y, "近 3 年營收"), },
}
RATINGS[("tech", "的技術堆疊與開發工具有哪些？")] = {  # 新句型
    "台灣大哥大": (Y, "技術堆疊"), "聯合報": (Y, "技術堆疊"), "叡揚資訊": (Y, "技術堆疊"), "神通資訊": (Y, "技術堆疊"),
    "藍新資訊": (U, "業務【公司自述】，有列平台與產品；該公司的技術堆疊段落沒排第 1"), "凱基證券": (Y, "技術堆疊"),
    "華電聯網": (Y, "技術堆疊（內容：查無語言與框架，只列主題）"), "中華網龍": (Y, "技術堆疊"), }


def measure(candidates):
    """{(kind, tail): {公司: top1 dict 或 None}}"""
    out = {}
    for kind, tails in candidates.items():
        for tail in tails:
            rows = {}
            for label, name in appmod.LIVE_COMPANIES:
                h = search(f"{label}{tail}", company=name, gate=False, dedupe=True)
                rows[label] = {"h": h[0]["heading_path"], "f": h[0]["file"], "s": h[0]["score"], "t": h[0]["text"][:160]} if h else None
            out[(kind, tail)] = rows
    return out


def blocked(r):
    return r is None or r["s"] < retrieval.NOT_FOUND_THRESHOLD


def table(kind_tails, res):
    L = ["| 句型 | 公司 | 問句 | 第 1 名標題 | 分數 | 被門檻擋住 | 第 1 名合理 | 理由 |", "|---|---|---|---|---|---|---|---|"]
    tot = {"b": 0, Y: 0, N: 0, U: 0}
    for kind, tail in kind_tails:
        for label, _ in appmod.LIVE_COMPANIES:
            r = res[(kind, tail)][label]
            code, why = RATINGS[(kind, tail)][label]
            b = blocked(r)
            tot["b"] += b
            tot[code] += 1
            L.append(f"| {KINDS[kind]} | {label} | {label}{tail} | {r['h'][-40:]} ({r['f'][:12]}) | {r['s']:.3f} | {'是' if b else '否'} | {code} | {why} |")
    return L, tot


def main():
    res = measure(CANDIDATES)
    base = [(k, c[0]) for k, c in CANDIDATES.items()]
    final = [(k, appmod.FAQ[k][1]) for k in CANDIDATES]
    Lb, tb = table(base, res)
    Lf, tf = table(final, res)
    nc = len(appmod.LIVE_COMPANIES)
    total = nc * len(CANDIDATES)  # 句型數 x 公司數；公司清單變動時自動跟著變
    blk = lambda kt: sum(blocked(r) for r in res[kt].values())
    out = ["# 常用問題按鈕檢查（票 19，票 23 重跑）", "",
           f"{len(CANDIDATES)} 個句型 x {nc} 家現場公司 = {total} 題。問句與介面相同（句型代入公司名、只搜該公司、去重開），不套門檻（`gate=False`）。門檻 `NOT_FOUND_THRESHOLD` = {retrieval.NOT_FOUND_THRESHOLD}，**沒有調整**；檢索與評分程式沒有改。",
           "「被門檻擋住」＝第 1 名分數低於門檻，畫面會顯示「可能沒有答案」。「第 1 名合理」是人看過段落標題與內容後判斷（見 `RATINGS`）：合理＝是該公司該主題的段落（內容是「查無」但標題對，也算合理，因為答案就是查無）；不確定＝標題或內容看不出能不能回答。",
           f"票 23：奧衍、尼諾思、醫宇宙已移出系統，這份檢查只剩 {nc} 家；人工判斷沿用留下來的公司原本的判斷，沒有重判。",
           "重跑：`python -X utf8 eval/button_check.py`（需要語料與模型，約 4 分鐘）。",
           "", "## 一、原句型（改前）", "", f"被擋住 {tb['b']} / {total}；第 1 名合理 {tb[Y]}、不合理 {tb[N]}、不確定 {tb[U]}。", ""] + Lb
    out += ["", f"## 二、候選句型試跑（每個句型 {nc} 家公司）", "",
            "「被擋住」是真的分數。「標題含主題字」是自動粗判（第 1 名的標題、檔名或前 160 字含主題字），只能當參考；原句型與改後句型的合理數在其他兩節，是人工判斷。", "",
            f"| 句型 | 句尾 | 被擋住 / {nc} | 標題含主題字 / {nc} | 選用 |", "|---|---|---|---|---|"]
    for kind, tails in CANDIDATES.items():
        for tail in tails:
            rows = res[(kind, tail)]
            px = sum(bool(r and re.search(PROXY[kind], r["h"] + r["f"] + r["t"])) for r in rows.values())
            use = "改後" if tail == appmod.FAQ[kind][1] and tail != tails[0] else ("原句型（維持）" if tail == tails[0] and tail == appmod.FAQ[kind][1] else ("原句型" if tail == tails[0] else ""))
            out.append(f"| {KINDS[kind]} | {tail} | {sum(blocked(r) for r in rows.values())} | {px} | {use} |")
    out += ["", "## 三、選定句型（改後）", "", f"被擋住 {tf['b']} / {total}；第 1 名合理 {tf[Y]}、不合理 {tf[N]}、不確定 {tf[U]}。", ""] + Lf
    out += ["", "## 四、前後比較", "", "| | 改前 | 改後 |", "|---|---|---|",
            f"| 被門檻擋住 | {tb['b']} / {total} | {tf['b']} / {total} |", f"| 第 1 名合理 | {tb[Y]} | {tf[Y]} |", f"| 第 1 名不合理 | {tb[N]} | {tf[N]} |", f"| 不確定 | {tb[U]} | {tf[U]} |"]
    out += ["", "## 五、仍被擋住的組合（改後）", "", "| 公司 | 句型 | 分數 | 第 1 名 | 說明 |", "|---|---|---|---|---|"]
    for kind, tail in final:
        for label, _ in appmod.LIVE_COMPANIES:
            r = res[(kind, tail)][label]
            if blocked(r):
                out.append(f"| {label} | {KINDS[kind]} | {r['s']:.3f} | {r['h'][-30:]} | {RATINGS[(kind, tail)][label][1]} |")
    tech_hit = lambda kt: sum(bool(r and "技術堆疊" in r["h"]) for r in res[kt].values())
    k0, k1 = ("tech", CANDIDATES["tech"][0]), ("tech", appmod.FAQ["tech"][1])
    out += ["", "## 六、選定理由（數字由程式算）", "",
            f"- 只改「用什麼技術」：改成「{appmod.FAQ['tech'][1]}」。第 1 名是「技術堆疊」段落的公司從 {tech_hit(k0)} 家變 {tech_hit(k1)} 家，被擋住從 {blk(k0)} 家變 {blk(k1)} 家。原因是這個說法接近段落標題與內容用語。這是句型措辭的效果，不是門檻或檢索的改變。"]
    for kind in ("what", "jobs", "fin"):
        o = (kind, CANDIDATES[kind][0])
        best = min(CANDIDATES[kind], key=lambda t: blk((kind, t)))
        out.append(f"- 「{KINDS[kind]}」不改：原句型被擋住 {blk(o)} 家；被擋住最少的候選「{best}」是 {blk((kind, best))} 家。")
    out += ["- 這份檢查只量第 1 名是否被門檻擋住與標題是否對題；被擋住的組合（第五節）多半是資料少或基本資料登記表排第 1。門檻沒有動。",
            f"- 限制：「合理」是人工判斷，只有我一個人看過，「不確定」{tf[U]} 題沒有定論；{total} 題是現場公司全部組合，不是抽樣，但分數會隨語料更新而變。"]
    Path(__file__).with_name("button_check.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"被擋住 {tb['b']} -> {tf['b']}；合理 {tb[Y]} -> {tf[Y]}")


if __name__ == "__main__":
    main()

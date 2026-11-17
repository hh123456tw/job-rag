"""讀 results.json，算彙整並寫 summary.md（人工判斷寫在 JUDGE）。python -X utf8 eval_per3/summarize.py"""
import json, re, statistics as st
from pathlib import Path
D = Path(__file__).parent
r = json.loads((D / "results.json").read_text(encoding="utf-8"))
JUDGE = {  # 人工逐題判斷：(a)更完整 (b)差不多 (c)更差；FAB＝編造／無依據
 "x01": ("b", "8 家都有、薪資數字都有出處；3 段版每家多列 1~2 個職缺並多一句總結，內容更多但不更準。"),
 "x02": ("a", "3 段版找到神通資訊的 Python／Django 對接職缺 [20]，2 段版對神通寫「資料沒寫」；台灣大、聯合報也多列職缺。"),
 "x03": ("b", "兩版 8 家都有 AI 職缺；3 段版每家多一兩個職缺名，但描述變短；多帶 1 個勉強算 AI 的職缺（台灣大「AI 工具輔助維運」，用「另有…提到」帶過）。"),
 "x04": ("a", "3 段版補到華電聯網「需出差」職缺 [24]（2 段版只有「無需出差」）；2 段版放了與出差無關的台灣大遠端句。"),
 "x05": ("b", "台灣大、神通、叡揚、聯合報、華電都有 Java 依據；2 段版對凱基多一句 JAVA 工程師 EDM 說明，3 段版只寫「資料沒寫」；互有取捨。"),
 "x06": (None, "兩版都被 CROSS_FLOOR 擋住（最高分 0.484 < 0.534），沒呼叫 DeepSeek；本題應有答案，是漏答。"),
 "x07": ("b", "兩版都是叡揚、台灣大、華電、神通有雲端職缺；3 段版細節較多，但凱基一行自相矛盾（引用雲端架構又說資料沒寫），藍新一行冗長。"),
 "x08": ("b", "兩版都找到神通、聯合報前端職缺；3 段版多了台灣大「加分提到 React／Vue」與神通全端職缺，但其餘 5 家一律只寫「資料沒寫」，2 段版會說明各家有什麼職缺。"),
 "x09": ("a", "3 段版對叡揚給出 2025 營收 20.19 億 [10]（2 段版寫「近一年營收沒寫」），華電、藍新數字也較新；比較結論仍有依據、未下主觀結論。"),
 "x10": ("c", "FAB：3 段版寫台灣大「列出 Docker 相關技能……Docker 僅見於職缺條件與擅長工具欄」，但送進去的 [6][7] 沒有 Docker 一詞（只有 Kubernetes、Jenkins）；2 段版正確寫「資料中沒有提到 Docker」。"),
 "x11": ("b", "兩版都只列資料、不排名；3 段版對台灣大、神通列出更多後端職缺，無後端的公司說得較清楚，但叡揚多帶一句 salary.tw 廣告薪資，離題。"),
 "x12": ("b", "兩版都是 8 家一長段（約 1500 completion token）；3 段版多放藍新重複獎項、凱基「智慧牧羊犬屬數位創新部」等非新聞，同時刪掉部分細節；無編造。"),
}
NOSUB = "(?:（[^）]*）)?[：:]\\s*資料(?:中)?(?:沒寫|沒有)"


def subst(ans, c):
    occ = [m.start() for m in re.finditer(re.escape(c), ans)]
    return any(not re.match(NOSUB, ans[i + len(c):]) for i in occ)


for k, d in r.items():
    if "answer" in d:
        d["substantive"] = sorted(c for c in d["relevant"] if subst(d["answer"], c))
        d["missed_substantive"] = sorted(set(d["relevant"]) - set(d["substantive"]))
(D / "results.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


def agg(per, ids):
    rows = [r[f"{i}_per{per}"] for i in ids]
    done = [x for x in rows if "answer" in x]
    tot = sum(len(x["relevant"]) for x in rows)
    return dict(called=len(done), cov_mention=sum(len(set(x["relevant"]) & set(x["mentioned"])) for x in done) / tot,
                cov_subst=sum(len(x["substantive"]) for x in done) / tot,
                miss_subst_q=sum(bool(x["missed_substantive"]) for x in done) + (len(rows) - len(done)),
                seg=st.mean(x["n_hits"] for x in done), pt=st.mean(x["usage"]["prompt_tokens"] for x in done),
                ct=st.mean(x["usage"]["completion_tokens"] for x in done), secs=st.mean(x["secs"] for x in done),
                chars=st.mean(x["chars"] for x in done))


ids = [f"x{i:02d}" for i in range(1, 13)]
A = {p: agg(p, ids) for p in (2, 3)}
L = ["# per=2 vs per=3 端到端比較（DeepSeek 真實呼叫，單次，每題每設定 1 次無重試）", "",
     "語料：廠商深查（新版）；模型＝answer.py DEFAULT_MODEL；流程＝app._cross_hits → _low_cross → answer(cross=True)，prompt 與 app 同一份。",
     "涵蓋率分母＝該出現的公司（relevant：程式以題檔 keywords 比對公開段落，非人工標註，會高估）。「提到」＝答案出現公司名（含「資料沒寫」那行）；"
     "「實質」＝公司名後不是「資料沒寫／沒有」。x06 被門檻擋住，涵蓋率算 0 並計入分母與「有漏公司題數」。平均值只算有呼叫 DeepSeek 的 11 題。", "",
     "## 彙整（12 道有答案題）", "", "| 指標 | per=2 | per=3 |", "|---|---|---|"]


def row(name, f):
    L.append(f"| {name} | {f(A[2])} | {f(A[3])} |")


row("實際呼叫 DeepSeek 題數", lambda a: f"{a['called']}/12")
row("涵蓋率（提到）", lambda a: f"{a['cov_mention']:.3f}")
row("涵蓋率（實質）", lambda a: f"{a['cov_subst']:.3f}")
row("漏公司題數（實質；含 x06）", lambda a: str(a["miss_subst_q"]))
row("平均送進段數", lambda a: f"{a['seg']:.1f}")
row("平均 prompt_tokens", lambda a: f"{a['pt']:.0f}")
row("平均 completion_tokens", lambda a: f"{a['ct']:.0f}")
row("平均回應秒數", lambda a: f"{a['secs']:.2f}")
row("平均答案字數", lambda a: f"{a['chars']:.0f}")
cnt = {k: sum(1 for v in JUDGE.values() if v[0] == k) for k in "abc"}
L += ["", "人工判斷（3 段版相對 2 段版，11 道已回答題；x06 兩版都被擋，不評）：",
      f"- (a) 更完整：{cnt['a']}　(b) 差不多：{cnt['b']}　(c) 更差：{cnt['c']}", "",
      "## 無答案題（u01–u03）", "", "| 題 | 問句 | 最高分 | per=2 | per=3 |", "|---|---|---|---|---|"]
for i in ("u01", "u02", "u03"):
    a, b = r[f"{i}_per2"], r[f"{i}_per3"]
    f = lambda x: "門檻擋住，未呼叫" if x["blocked"] else "呼叫"
    L.append(f"| {i} | {a['question']} | {a['top']:.3f} | {f(a)} | {f(b)} |")
L += ["", "三題都由 CROSS_FLOOR(0.534) 擋住，沒用到 DeepSeek 的拒答能力；最高分與 per 無關，兩版相同。", "",
      "## 逐題表", "", "| 題 | 版本 | 段 | prompt_tok | compl_tok | 秒 | 字數 | 實質有寫/該出現 | 漏（實質） | 含「資料沒寫」類句 |", "|---|---|---|---|---|---|---|---|---|---|"]
for i in ids:
    for p in (2, 3):
        x = r[f"{i}_per{p}"]
        if "answer" not in x:
            L.append(f"| {i} | per{p} | {x['n_hits']} | - | - | - | - | 0/{len(x['relevant'])} | 全部（被門檻擋，top {x['top']:.3f}） | - |")
        else:
            L.append(f"| {i} | per{p} | {x['n_hits']} | {x['usage']['prompt_tokens']} | {x['usage']['completion_tokens']} | {x['secs']} | {x['chars']} | "
                     f"{len(x['substantive'])}/{len(x['relevant'])} | {'、'.join(x['missed_substantive']) or '無'} | {'是' if x['has_nodata_phrase'] else '否'} |")
L += ["", "## 人工判斷（逐題一句）", "", "| 題 | 問句 | 判斷 | 理由 |", "|---|---|---|---|"]
for i, (j, why) in JUDGE.items():
    L.append(f"| {i} | {r[i + '_per2']['question']} | {'(' + j + ')' if j else '不評'} | {why} |")
L += ["", "## 編造／無依據",
      "- x10 per=3：台灣大哥大的 Docker 說法無依據（見上）。",
      "- 抽查對得上送進去段落：x01 實習生薪資、x04 華電出差、x07 Azure、x09 叡揚 20.19 億／藍新 5.77 億／華電 18.2 億、x12 藍新獎項。未逐字核對全部 21 份答案。",
      "- 「資料沒寫」有時過度：x02 per=2 對神通寫「資料沒寫」，但語料有 Python／Django 相關職缺（3 段版才取到）。", "",
      "## 限制",
      "- 單次輸出，DeepSeek 有隨機性；題數 12，a/b/c 差異不具統計意義。",
      "- 涵蓋率的 relevant 由關鍵字定義，不是人工標註。",
      "- 人工判斷只由一人（本次執行者）完成，未複核。"]
(D / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[8:22]))

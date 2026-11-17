"""由原題檔產生新版用的題檔副本，只改 gold；寫出 gold_remap.md。python -X utf8 eval_compare/make_remap.py"""
import sys, json, copy
sys.path.insert(0, ".")
from job_rag import retrieval as r
from job_rag.evalset import _squash
NEW = r"C:\claude\aipe04期末\履歷\廠商深查_新版"
segs = [s for s in r._segments(str(r._corpus_dir(NEW).resolve())) if not s["excluded"]]


def ok(g):
    u = [s for s in segs if s["file"] == g["file"] and (s["heading_path"] == g["heading"] or s["heading_path"].startswith(g["heading"] + " > "))]
    return bool(u) and any(_squash(g["quote"]) in _squash(s["text"]) for s in u)


OPEN = "目前開放職缺"


def G(f, h, q):
    return {"file": f, "heading": h if h == OPEN else f"{OPEN} > {h}", "quote": q}


F30, F31, F32, F33, F34, F35, F36, F37 = ("30_104職缺更新_台灣大哥大.md", "31_104職缺更新_聯合報.md", "32_104職缺更新_叡揚資訊.md",
    "33_104職缺更新_神通資訊.md", "34_104職缺更新_藍新資訊.md", "35_104職缺更新_凱基證券.md", "36_104職缺更新_華電聯網.md", "37_104職缺更新_中華網龍.md")
R = {
 ("questions", "j03"): ([G(F33, "60076X0_後端工程師(Node.js)（104 職缺代碼 8y67b）", "用 Node.js（JavaScript／TypeScript）開發與維護企業級平台後端")], "神通 Node.js 後端職缺仍在，內容一致"),
 ("questions", "j04"): ([G(F30, "I97 Kubernetes 平台工程師（8xjjo）", "3 年以上 DevOps／SRE／平台工程與 2 年以上 Kubernetes")], "職缺仍在；3 年（K8s 2 年）不變"),
 ("questions", "j07"): ([G(F31, "【戰略部】數據優化師(數據分析)（7qtdo）", "月薪 35,000 元以上")], "月薪 35,000 以上不變"),
 ("questions", "j09"): ([G(F33, "K026KB6_C++/AI 應用工程師（104 職缺代碼 93vim）", "不需出差")], "仍為不需出差；兩個舊金標併成一個新段"),
 ("questions", "j10"): ([G(F37, "AI 應用研發工程師（104 職缺代碼 9523j）", "必備 Python、TypeScript 或其他後端語言")], "技能不變；兩個舊金標併成一個新段"),
 ("questions", "j11"): ([G(F34, "AI前線部署工程師（8uol0）", "GenAI、Agentic AI、RAG、MCP、REST API、Linux、Docker、Kubernetes")], "技能不變；兩個舊金標併成一個新段"),
 ("questions", "j12"): ([G(F33, "60296BD_AI 工程師（生成式 AI）（104 職缺代碼 94rqp）", "用 Python 與 FastAPI 建構後端 API 與 AI 服務，串接 LLM API")], "技能不變；兩個舊金標併成一個新段"),
 ("questions", "j13"): ([G(F36, "資深研發工程師－研發一部（汐止）（104 職缺代碼 8zclg）", "必備為 Python 開發 3 年以上")], "Python 3 年、Linux、Docker 不變；兩個舊金標併成一個新段"),
 ("questions", "j14"): ([G(F35, "【數位創新部】AI Solution 工程師/架構師（91qox）", "3 年以上 AI 系統或大型軟體架構設計經驗")], "3 年以上、AI 系統／架構經驗不變；三個舊金標併成一個新段"),
 ("questions_heldout", "h19"): ([G(F36, "高級工程師（高雄）資料庫（104 職缺代碼 7q8te）", "擅長工具欄為 MySQL、Oracle、PL/SQL")], "資料庫技能不變"),
 ("questions_real", "r01"): ([G(F30, OPEN, "年薪約81~108萬")], "舊金標是 A_ 檔整個台哥大區塊；新版換成 30 檔整個「目前開放職缺」區塊（粗對粗）；01_台灣大哥大 的金標仍在，保留"),
 ("questions_real", "r02"): ([G(F32, OPEN, "月薪 35,000~55,000")], "同上；03_叡揚資訊 的金標仍在，保留"),
 ("questions_real", "r03"): ([G(F33, OPEN, "月薪 45,000 元以上")], "舊兩個金標（B_、網址2）都沒了；換成 33 檔整個「目前開放職缺」區塊；月薪 42,000／45,000 以上並存，事實仍成立"),
 ("questions_real", "r06"): ([G(F36, OPEN, "公司：華電聯網股份有限公司")], "舊兩個金標都沒了；換成 36 檔整個職缺區塊"),
 ("questions_real", "r07"): ([G(F31, OPEN, "數據發展部")], "舊兩個金標都沒了；換成 31 檔整個職缺區塊"),
}
md = ["# gold 對應表（舊版題檔 -> 新版題檔副本）", "",
      "新版語料已刪掉 8 家公司在 `104\\` 資料夾的舊職缺段落，改放 30～37 號檔。原題檔（eval\\、主專案）沒有改；新版評估用 eval_compare\\ 的副本，只改 gold。",
      "判定方式：對原題檔每個可回答題的每個 gold，檢查新版「檔名＋標題路徑」下是否還有段落、段落是否還含 quote（空白不計）。對不到的才列在下面。",
      "事實檢查：逐題讀新段落，確認題目的事實（技能、年資、薪資、出差）與舊 gold 一致。**15 題都沒有事實變動，沒有需要從新版統計排除的題。**", "",
      "| 題檔 | 題號 | 題目 | 舊 gold（檔名 / 標題） | 新 gold（檔名 / 標題）| 依據 |", "|---|---|---|---|---|---|"]
for qf in ("questions", "questions_heldout", "questions_real"):
    d = json.load(open(f"eval/{qf}.json", encoding="utf-8"))
    nd = copy.deepcopy(d)
    for q, nq in zip(d["questions"], nd["questions"]):
        key = (qf, q["id"])
        if key in R:
            new, why = R[key]
            keep = [g for g in q["gold"] if ok(g)]
            nq["gold"] = keep + new
            for g in nq["gold"]:
                assert ok(g), (key, g)
            old = "<br>".join(f'{g["file"]} / {g["heading"][:36]}' + ("（仍有效，保留）" if g in keep else "") for g in q["gold"])
            nw = "<br>".join(f'{g["file"]} / {g["heading"][:50]}' for g in new)
            who = f'（{q["company"]}）' if q.get("company") else ""
            md.append(f'| {qf} | {q["id"]} | {q["question"]}{who} | {old} | {nw} | {why} |')
        elif q["answerable"]:
            assert all(ok(g) for g in q["gold"]), key
    json.dump(nd, open(f"eval_compare/{qf}_new.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
md += ["", "其餘可回答題的 gold 在新版全部仍有效，不動（程式已逐題斷言）。",
       "題檔摘要（questions_digest）會因 gold 改變而不同，不可拿來和舊結果檔的 digest 比。",
       "", "## 注意（粗粒度 gold 偏向新版）",
       "r01、r02、r03、r06、r07 的金標指到整個「目前開放職缺」區塊（舊版也是整個公司區塊），區塊內任何一個職缺段命中都算；新版區塊大很多，這 5 題的 Hit 較容易。判讀時請看這 5 題的個別名次。"]
open("eval_compare/gold_remap.md", "w", encoding="utf-8").write("\n".join(md) + "\n")
print("ok", len(R))

"""把 gold 對應與補強寫進 eval/ 內原題檔。python -X utf8 eval_compare/apply_gold.py"""
import json
P = "待使用者確認"
S_GOLD = P + "（gold 於 2026-11-17 因語料換新版而更新）"
S_ADD = P + "（gold 於 2026-11-17 因語料換新版而更新；新增補充檔的正確段落）"
S_FLIP = P + "（2026-11-17 因新語料已含答案，由不可回答改標為可回答，非為提高分數）"
REMAP = {"questions": "j03 j04 j07 j09 j10 j11 j12 j13 j14", "questions_heldout": "h19", "questions_real": "r01 r02 r03 r06 r07"}
G = lambda f, h, q: {"file": f, "heading": h, "quote": q}
ADD = {
 ("questions", "c01"): [G("24_補充_藍新資訊.md", "近一年新聞 > 2025 年底原廠夥伴獎項", "HPE FY25 最佳合作夥伴獎")],
 ("questions", "s03"): [G("26_補充_華電聯網.md", "業務與財務 > 政府標案與在手專案", "110 件政府標案，得標總金額近 83 億元")],
 ("questions", "s04"): [G("22_補充_叡揚資訊.md", "業務與財務 > 2025 年財務結果", "20.19 億元，年增 16.33%")],
 ("questions_heldout", "h01"): [G("20_補充_台灣大哥大.md", "業務與財務 > 2025 年第四季與全年細項", "EPS 4.77 元")],
 ("questions_heldout", "h02"): [G("21_補充_聯合報.md", "技術堆疊 > Google Cloud 資料與運算架構", "使用的產品包括 BigQuery、Vertex AI、Compute Engine")],
 ("questions_heldout", "h05"): [G("24_補充_藍新資訊.md", "基本資料 > 設立與資本市場歷程", "每股 68 元掛牌上櫃"),
                                G("24_補充_藍新資訊.md", "近一年新聞 > 2026 年上櫃審議到掛牌", "承銷價每股 68 元掛牌上櫃")],
 ("questions_heldout", "h07"): [G("26_補充_華電聯網.md", "基本資料 > 策略夥伴與客戶群", "政府單位（交通部、國防單位、地方政府）、電信業"),
                                G("26_補充_華電聯網.md", "業務與財務 > 2025 年營收結構與客戶組成", "企業 44.1%、政府 31.5%、電信 24.4%")],
 ("questions_heldout", "h17"): [G("23_補充_神通資訊.md", "技術堆疊 > Agent Builder 企業 AI 一體機的軟硬體", "MiTAC Agent Builder 企業 AI 一體機")],
 ("questions_real", "r10"): [G("27_補充_中華網龍.md", "業務與財務 > 2024 至 2026 年營收與獲利", "2025 年營收 3.96 億元")],
}
for f, ids in REMAP.items():
    p = f"eval/{f}.json"
    d = json.load(open(p, encoding="utf-8"))
    new = {q["id"]: q for q in json.load(open(f"eval_compare/{f}_new.json", encoding="utf-8"))["questions"]}
    for q in d["questions"]:
        k = (f, q["id"])
        if q["id"] in ids.split():
            q["gold"] = new[q["id"]]["gold"]; q["status"] = S_GOLD
        if k in ADD:
            q["gold"] += ADD[k]; q["status"] = S_GOLD if q["id"] in ids.split() else S_ADD
        if k == ("questions_heldout", "h40"):
            q.update(type="跨公司", answerable=True, keywords=["家庭日、社團"], status=S_FLIP)
            q.pop("trap"); q.pop("absence_keywords")
        if k == ("questions_real", "r20"):
            q.update(type="跨公司", answerable=True, keywords=["國內外員旅補助", "旅遊與活動補助"], status=S_FLIP)
            q.pop("absence_keywords")
        # 已讀過命中段落、確認不回答題目的關鍵字
    open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")

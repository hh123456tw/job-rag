"""核對 Codex 出的跨公司驗證題：python -X utf8 eval/gen_cross/check.py <raw 輸出檔> [要寫出的題檔]
每題檢查：題型在清單內；問句沒有公司名；符合的公司都是 8 家現場公司、2–6 家；每家符合的公司剛好一筆證據，
證據的檔案／標題／引文逐字存在（沿用 eval/gen100/verify.py）；不可回答題的關鍵字在整份語料 0 筆命中；與現有題檔不重複。
全部通過才寫題檔（加上題號與說明）。有問題就列出來、不寫檔，結束碼 1。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "gen100"))
from verify import check_gold, corpus  # noqa: E402

LIVE = ["台灣大哥大", "聯合報", "叡揚資訊", "神通資訊", "藍新資訊", "凱基證券", "華電聯網", "中華網龍"]
KINDS = {"技術名詞": 6, "職缺類型": 4, "薪資與福利": 3, "地點": 3, "公司業務與新聞": 4, "不可回答": 4}
norm = lambda s: re.sub(r"[\s？?，,。]", "", s)


def load(path):
    t = Path(path).read_text(encoding="utf-8").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    return json.loads(t[t.index("["):t.rindex("]") + 1])


def problems(q, corp, existing, seen):
    p = []
    if q.get("kind") not in KINDS:
        p.append("題型不在清單內")
    if any(c in q["question"] for c in LIVE):
        p.append("問句有公司名")
    n = norm(q["question"])
    if n in seen or n in existing:
        p.append("重複")
    cos, gold = q.get("companies") or [], q.get("gold") or []
    if q.get("answerable"):
        if not 2 <= len(cos) <= 6 or set(cos) - set(LIVE) or len(set(cos)) != len(cos):
            p.append(f"符合公司數或名稱不對：{cos}")
        if sorted(g.get("company") for g in gold) != sorted(cos):
            p.append("證據與符合公司對不上（每家剛好一筆）")
        for g in gold:
            e = check_gold(g)
            if e:
                p.append(f"{e}: {g.get('company')}|{g['file']}|{g['heading'][:24]}|{g['quote'][:18]}")
            elif LIVE and not any(g["file"].startswith(x) for x in _prefix(g.get("company"))):
                p.append(f"證據檔不是這家公司的：{g.get('company')}|{g['file']}")
        if not q.get("keywords"):
            p.append("沒有 keywords")
    else:
        if cos or gold:
            p.append("不可回答題不該有公司或證據")
        kws = q.get("absence_keywords") or []
        if not kws:
            p.append("沒有 absence_keywords")
        for k in kws:
            hit = [name for name, text in corp.items() if k in text]
            if hit:
                p.append(f"關鍵字 {k} 在語料出現：{hit[:3]}")
    return p


PREFIX = {"台灣大哥大": ("01", "20", "30"), "聯合報": ("02", "21", "31"), "叡揚資訊": ("03", "22", "32"), "神通資訊": ("04", "23", "33"),
          "藍新資訊": ("05", "24", "34"), "凱基證券": ("06", "25", "35"), "華電聯網": ("07", "26", "36"), "中華網龍": ("09", "27", "37")}


def _prefix(company):
    return tuple(x + "_" for x in PREFIX.get(company, ()))


def main():
    qs = load(sys.argv[1])
    corp = corpus()
    existing = set()
    for f in ("questions_heldout.json", "questions_cross.json", "questions.json", "questions_real.json"):
        existing |= {norm(q["question"]) for q in json.loads((HERE.parent / f).read_text(encoding="utf-8"))["questions"]}
    seen, bad = set(), 0
    for i, q in enumerate(qs):
        pr = problems(q, corp, existing, seen)
        seen.add(norm(q["question"]))
        if pr:
            bad += 1
            print("BAD", i, q["question"], pr[:4])
    kinds = Counter(q.get("kind") for q in qs)
    if dict(kinds) != KINDS:
        bad += 1
        print("BAD 題型題數不符：", dict(kinds))
    print(f"共 {len(qs)} 題，有問題 {bad} 項")
    if bad:
        sys.exit(1)
    if len(sys.argv) > 2:
        out = [dict(q, id=f"v{n:02d}") for n, q in enumerate(qs, 1)]
        Path(sys.argv[2]).write_text(json.dumps({
            "說明": "跨公司驗證題 24 題（2026-11-18／19）。由 Codex CLI 預設 GPT 模型出題（提示詞 eval/gen_cross/prompt.txt），口吻直白、不刻意換說法；"
                    "題型事先定好：技術名詞 6、職缺類型 4、薪資與福利 3、地點 3、公司業務與新聞 4、不可回答 4。"
                    "每題附符合的公司名單，每家一筆證據（檔案／標題／引文已用程式逐字核對）。出題時沒有看任何檢索或評分結果；出完只評一次，不得為了結果改題或調參數。"
                    "限制：單一模型出題；「符合的公司有沒有列全」只有出題模型自己掃語料的保證，沒有人工確認。",
            "questions": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("已寫", sys.argv[2])


if __name__ == "__main__":
    main()

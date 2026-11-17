import sys, json, re
sys.path.insert(0, ".")
from job_rag import retrieval as r
from job_rag.evalset import _squash
OLD=r"C:\claude\aipe04期末\履歷\廠商深查"; NEW=r"C:\claude\aipe04期末\履歷\廠商深查_新版"
def load(p): return [s for s in r._segments(str(r._corpus_dir(p).resolve())) if not s["excluded"]]
S={"old":load(OLD),"new":load(NEW)}
EXTRA={ # 我另加的同義詞／相關詞（原題檔的 absence_keywords 之外）
 "u02":["多益","TOEIC","英檢","英文","語文"],"u03":["玩家","活躍","用戶數","下載"],
 "u06":["休假","特休","假"],"u07":["遠端","居家","在家","WFH","混合"],
 "u08":["平均年薪","平均薪","年薪","薪資中位"],"h26":["颱風","天災","停班"],"h27":["持股","信託"],"h28":["津貼","交通","補助"],
 "h29":["心理","諮商","EAP","諮詢"],"h30":["育嬰","育兒","產假","托育"],"h31":["營收目標","目標","預計營收","營收"],"h32":["下載","尋秦記"],
 "h33":["AI 部","AI部","工程師人數","人"],"h34":["廣達"],"h35":["鴻海"],"h36":["富邦"],"h37":["天氣","氣象","下雨"],"h38":["自傳","履歷"],"h39":["哺乳","育嬰室","托育"],"h40":["社團"],
 "r14":["餐廳","員工餐","食堂","午餐"],"r15":["尾牙","獎品","抽獎"],"r16":["托嬰","幼兒園","托育","育兒"],"r17":["宿舍","住宿"],"r18":["陪產"],"r19":["股價","收盤","股票"],"r20":["旅遊","員旅"],
 "x_u01":["員工餐廳","餐廳","食堂"],"x_u02":["寵物"],"x_u03":["Golang","Go "," Go","Go,","Go、","Go／","Go)"],
}
qs=[]
for f in ["questions","questions_heldout","questions_real","questions_cross"]:
    for q in json.load(open(f"eval/{f}.json",encoding="utf-8"))["questions"]:
        if not q["answerable"]:
            kws=q.get("absence_keywords") or q.get("keywords")
            tag=f"{f}:{q['id']}"
            qid=q["id"] if f!="questions_cross" else "x_"+q["id"]
            if f=="questions": qid=q["id"]
            qs.append((tag,qid,q,kws))
out={}
for tag,qid,q,kws in qs:
    ex=EXTRA.get(qid,[]) if not (tag.startswith("questions_cross") and False) else []
    row={"q":q["question"],"orig_kw":kws,"old":{},"new":{}}
    for v in ("old","new"):
        for kw in list(dict.fromkeys(kws+ex)):
            k=_squash(kw)
            hits=[s for s in S[v] if k in _squash(s["text"])]
            if hits:
                row[v][kw]=[(s["file"],s["heading_path"][:70],len(hits)) for s in hits[:0]]+[(s["file"],s["heading_path"][:80]) for s in hits]
    out[tag]=row
json.dump(out,open("eval_compare/contam_raw.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
for tag,row in out.items():
    print("==",tag,row["q"],"| orig_kw",row["orig_kw"])
    for v in ("old","new"):
        print("  ",v,{k:len(h) for k,h in row[v].items()})

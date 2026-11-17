import json,re
o=json.load(open("res_old.json",encoding="utf-8")); n=json.load(open("res_new.json",encoding="utf-8"))
K={"g01":["資本額"],"g02":["電信","業務"],"g03":["EPS","純益","獲利"],"g04":["業務","報","媒體"],"g05":["2026-","2026 年","2025 年"],"g06":["產品"],"g07":["資本額","員工","人數"],"g08":["Java","AWS","GCP","Azure","技術","Python","Spring"],
"g09":["資本額","員工","人數"],"g10":["系統整合","AIoT","業務"],"g11":["代理品牌","產品線","Cisco"],"g12":["2026-","2025-1"],"g13":["資本額"],"g14":["EPS","純益","獲利","營收"],"g15":["證券","經紀","承銷","業務"],"g16":["智慧","物聯網","業務","系統整合"],"g17":["資本額","員工","人數"],"g18":["產品","技術","AI"],"g19":["吞食天地","尋秦記","飄流幻境","遊戲"],"g20":["資本額","新聞","2026-"]}
# 需同時滿足：g07 g09 g17 g20 要兩類都有
BOTH={"g07":[["資本額"],["員工","人數"]],"g09":[["資本額"],["員工","人數"]],"g17":[["資本額"],["員工","人數"]],"g20":[["資本額"],["新聞","2026-","遊戲"]]}
def has(x,kws): return any(any(k in h["text"] for k in kws) for h in x["hits"])
def ok(q,x):
    if q in BOTH: return all(has(x,g) for g in BOTH[q])
    return has(x,K[q])
rows=[]
for a,b in zip(o["gap"],n["gap"]):
    q=a["id"]
    rows.append((q,a["top"],a["low"],a["n_job_top5"],ok(q,a),b["top"],b["low"],b["n_job_top5"],ok(q,b)))
    print(q,"old top %.3f low=%s job %d/5 ans=%s | new top %.3f low=%s job %d/5 ans=%s"%rows[-1][1:])
print("old: job-seg總數",sum(r[3] for r in rows),"/100; new",sum(r[7] for r in rows),"/100; 前5全職缺 old",sum(r[3]==5 for r in rows),"new",sum(r[7]==5 for r in rows),"; 含答案 old",sum(r[4] for r in rows),"new",sum(r[8] for r in rows),"; 低於門檻 old",sum(r[2] for r in rows),"new",sum(r[6] for r in rows))

import sys, json, re
sys.path.insert(0, ".")
from job_rag import retrieval as r
from job_rag.evalset import _squash
OLD=r"C:\claude\aipe04期末\履歷\廠商深查"; NEW=r"C:\claude\aipe04期末\履歷\廠商深查_新版"
def load(p): 
    return [s for s in r._segments(str(r._corpus_dir(p).resolve())) if not s["excluded"]]
S={"old":load(OLD),"new":load(NEW)}
def under(segs,g):
    return [s for s in segs if s["file"]==g["file"] and (s["heading_path"]==g["heading"] or s["heading_path"].startswith(g["heading"]+" > "))]
out={}
for qf in ("questions","questions_heldout","questions_real"):
    qs=json.load(open(f"eval/{qf}.json",encoding="utf-8"))["questions"]
    for q in qs:
        if not q["answerable"]: continue
        res={}
        for v in ("old","new"):
            ok=[]
            for g in q["gold"]:
                u=under(S[v],g)
                qt=_squash(g["quote"])
                ok.append(("seg" if u else "NOSEG", any(qt in _squash(s["text"]) for s in u)))
            res[v]=ok
        if res["new"]!=res["old"] or any(not (a=="seg" and b) for a,b in res["new"]):
            print(qf,q["id"],q["question"],"\n  old",res["old"],"\n  new",res["new"],"\n  gold",[(g["file"],g["heading"][:30]) for g in q["gold"]])

import sys, collections, json
sys.path.insert(0, ".")
from job_rag import retrieval as r
OLD=r"C:\claude\aipe04期末\履歷\廠商深查"; NEW=r"C:\claude\aipe04期末\履歷\廠商深查_新版"
for name,p in (("old",OLD),("new",NEW)):
    segs=r._segments(str(r._corpus_dir(p).resolve()))
    pub=[s for s in segs if not s["excluded"]]
    print(name,"all",len(segs),"public",len(pub))
    c=collections.Counter(s["company"] for s in pub); print(dict(c))
    if name=="new":
        for f in sorted({s["file"] for s in segs}):
            if f[:2] in ("20","21","22","23","24","25","26","27","30","31","32","33","34","35","36","37"):
                a=[s for s in segs if s["file"]==f]
                print(f, "pub",sum(not s["excluded"] for s in a),"excl",sum(s["excluded"] for s in a), {s["company"] for s in a})
                for s in a:
                    if s["excluded"]: print("   EXCL:",s["heading_path"][:80])

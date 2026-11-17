import sys, re
sys.path.insert(0, ".")
from job_rag import retrieval as r
NEW=r"C:\claude\aipe04期末\履歷\廠商深查_新版"
segs=[s for s in r._segments(str(r._corpus_dir(NEW).resolve())) if not s["excluded"]]
def show(kw, company=None, width=60, maxn=12, files=None):
    n=0
    for s in segs:
        if company and s["company"]!=company: continue
        if files and not s["file"][:2] in files: continue
        for m in re.finditer(re.escape(kw), s["text"]):
            a=max(0,m.start()-width); b=min(len(s["text"]),m.end()+width)
            print(f'  [{s["company"]}|{s["file"][:24]}|{s["heading_path"][-40:]}] ...{s["text"][a:b]!r}'); n+=1
            break
        if n>=maxn: break
if __name__=="__main__":
    kw=sys.argv[1]; co=sys.argv[2] if len(sys.argv)>2 and sys.argv[2]!="-" else None
    mx=int(sys.argv[3]) if len(sys.argv)>3 else 12
    show(kw,co,maxn=mx)

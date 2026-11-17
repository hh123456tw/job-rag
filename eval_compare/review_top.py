import json, sys
sys.path.insert(0, ".")
from job_rag import search, detect_company
from job_rag.evalset import _squash
ids={"questions":"c01 c06 s03 s04 s10 s14 j13","questions_heldout":"h01 h02 h05 h07 h17 h20","questions_real":"r10"}
for f,l in ids.items():
    qs={q["id"]:q for q in json.load(open(f"eval_compare/{f}_new.json",encoding="utf-8"))["questions"]}
    for i in l.split():
        q=qs[i]; co=q.get("company") or detect_company(q["question"])
        res=search(q["question"],company=co,k=10,gate=False,dedupe=True)
        print("##",f,i,q["question"],"| co",co)
        for n,h in enumerate(res[:3],1):
            hasq=any(_squash(g["quote"]) in _squash(h["text"]) for g in q["gold"])
            if not hasq and n<=2:
                print(f"  --{n}. {h['score']:.3f} {h['file']} | {h['heading_path']}\n{h['text'][:1100]}\n")

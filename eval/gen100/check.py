import json,sys,re,glob
from verify import *
def load(path):
    t=pathlib.Path(path).read_text(encoding="utf-8").strip()
    t=re.sub(r'^```(?:json)?\s*|\s*```$','',t)
    return json.loads(t)
CORP=corpus()
EX=[]
for f in ["questions_heldout.json","questions.json"]:
    EX+= [q["question"] for q in json.load(open("../"+f,encoding="utf-8"))["questions"]]
def norm(s): return re.sub(r'[\s？?，,。]','',s)
def problems(q,seen):
    p=[]
    t=q.get("type")
    if t not in("單一公司","職缺","跨公司","不可回答"): p.append("bad type")
    if t=="不可回答":
        if q.get("gold"): p.append("unans has gold")
        kws=q.get("absence_keywords") or []
        if not kws: p.append("no absence kw")
        for k in kws:
            hit=[n for n,x in CORP.items() if k in x]
            if hit: p.append(f"kw {k} in {hit[:3]}")
    else:
        if not q.get("gold"): p.append("no gold")
        for g in q.get("gold",[]):
            e=check_gold(g)
            if e: p.append(f"{e}: {g['file']}|{g['heading'][:30]}|{g['quote'][:20]}")
    n=norm(q["question"])
    if n in seen or any(n==norm(x) for x in EX): p.append("dup")
    return p
if __name__=="__main__":
    seen=set();tot=0;bad=0
    for f in sorted(glob.glob("raw/out_*.txt")):
        qs=load(f)
        print(f,len(qs))
        for q in qs:
            tot+=1;pr=problems(q,seen);seen.add(norm(q["question"]))
            if pr: bad+=1;print("  BAD",q["question"],pr[:3])
    print(tot,bad)

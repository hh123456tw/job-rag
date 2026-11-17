import json
o=json.load(open("res_old.json",encoding="utf-8")); n=json.load(open("res_new.json",encoding="utf-8"))
EXC={"h40","r20"}  # 新版污染題
def pool(r):
    A,U=[],[]
    for k in ("q30","q40","real20"):
        d=r[k]; ans=set(d["answerable"])
        for i,s in d["scores"].items():
            thr=d["thr"]["scoped"] if i in d["scoped"] else d["thr"]["plain"]
            (A if i in ans else U).append((k+":"+i,s,thr))
    return A,U
for v,r in (("old",o),("new",n)):
    A,U=pool(r)
    print(v,"answerable n",len(A),"min %.3f"%min(a[1] for a in A),"median %.3f"%sorted(a[1] for a in A)[len(A)//2],
          "| unans n",len(U),"max %.3f"%max(u[1] for u in U),"median %.3f"%sorted(u[1] for u in U)[len(U)//2])
    print("  現行門檻 誤擋可回答",[(a[0],round(a[1],3)) for a in A if a[1]<a[2]],"擋住無答案",sum(u[1]<u[2] for u in U),"/",len(U),"未擋",[(u[0],round(u[1],3)) for u in U if u[1]>=u[2]])
    for delta in (-0.04,-0.02,0,0.02,0.04):
        print("   門檻平移 %+.2f (未指定 %.2f／指定公司 %.2f)：誤擋 %d/%d，擋住無答案 %d/%d"%(delta,0.7+delta,0.62+delta,
          sum(a[1]<a[2]+delta for a in A),len(A),sum(u[1]<u[2]+delta for u in U),len(U)))
# 逐題分數變化
for k in ("q30","q40","real20"):
    for i,s in o[k]["scores"].items():
        t=n[k]["scores"][i]
        if abs(t-s)>=0.03: print(k,i,"old %.3f new %.3f (%+.3f)"%(s,t,t-s),"ans" if i in o[k]["answerable"] else "UNANS",o[k]["text"][i])
# 跨公司 floor
for v,r in (("old",o),("new",n)):
    rows=r["cross15"]["2"]; a=[x["top"] for x in rows if x["answerable"]]; u=[x["top"] for x in rows if not x["answerable"]]
    print(v,"cross15 floor0.534: ans min %.3f unans max %.3f"%(min(a),max(u)),"blocked_a",[x["id"] for x in rows if x["answerable"] and x["status"]=="low"],"blocked_u",sum(x["status"]=="low" for x in rows if not x["answerable"]),"/",len(u))
    for k in ("q40","real20"):
        c=r[k]["cross"]; print("  ",k,"cross-route: blocked_u",[x["id"] for x in c if not x["answerable"] and x["status"]=="low"],"unans passed",[x["id"] for x in c if not x["answerable"] and x["status"]!="low"],"ans blocked",[x["id"] for x in c if x["answerable"] and x["status"]=="low"])

import json,re,sys,pathlib,glob
ROOT=pathlib.Path(r"C:\claude\aipe04期末\履歷\廠商深查")
BAN=["面試","評價","風險","判斷","推測","矛盾","限制","未查到","對應","作戰"]
BANFILE=("00_","selfdata")
_cache={}
def sections(fn):
    if fn in _cache: return _cache[fn]
    lines=(ROOT/fn).read_text(encoding="utf-8").splitlines()
    stack=[];secs={}  # path-> text lines (including descendants)
    cur=[]
    for ln in lines:
        m=re.match(r'^(#{1,6})\s+(.*?)\s*$',ln)
        if m:
            lv=len(m.group(1));t=m.group(2)
            stack=[s for s in stack if s[0]<lv]+[(lv,t)]
            cur=[ " > ".join(x[1] for x in stack if x[0]>1) ]
            # register this path as start; descendants appended to all open ancestors
        for i,(lv,t) in enumerate(stack):
            if lv>1:
                p=" > ".join(x[1] for x in stack[:i+1] if x[0]>1)
                secs.setdefault(p,[]).append(ln)
    out={k:"\n".join(v) for k,v in secs.items()}
    _cache[fn]=out;return out
def check_gold(g):
    f=g["file"]
    if not (ROOT/f).is_file(): return "no file"
    if f.startswith(BANFILE) or "/" in f or "\\" in f: return "banned file"
    if any(b in g["heading"] for b in BAN): return "banned heading"
    s=sections(f)
    if g["heading"] not in s: return "heading not found"
    if g["quote"] not in s[g["heading"]]: return "quote not found"
    return None
def corpus():
    return {p.name:p.read_text(encoding="utf-8") for p in ROOT.rglob("*.md")}
if __name__=="__main__":
    pass

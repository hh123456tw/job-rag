import subprocess,json,sys,pathlib,re
from check import *
import mkprompts as M
# usage: regen.py  (reads raw/bad.json: list of {file,idx,company,type,question,problems})
bad=json.load(open("raw/bad.json",encoding="utf-8"))
procs=[]
for i,b in enumerate(bad):
    comp=b.get("company")
    base=M.COMMON
    if b["type"]=="不可回答":
        if comp:
            task=f"""
【你的任務】只針對「{comp}」，出 1 題 type="不可回答"（company="{comp}"）：貼近真實面試官會問、但整個語料資料夾裡完全沒有答案的題。gold 設 []，加 "absence_keywords": [2–4 個關鍵字]。
硬性要求：每個關鍵字都要用 grep -r 對整個語料資料夾（含所有子資料夾）確認「全語料 0 筆命中」，所以不要用「加班費、年終、試用、健檢、員工旅遊」這類常見詞；請選更具體的題材（例如特定福利項目名稱、特定內部制度、特定數字）。
不能與這些題重複或同題材：{json.dumps(b['avoid'],ensure_ascii=False)}。上一題失敗原因：{b['problems']}
"""
        else:
            task=f"""
【你的任務】出 1 題 type="不可回答"（不指定公司，問「哪些公司有 X」，X 是語料沒寫的福利或制度）。gold []，加 "absence_keywords": [2–4 個關鍵字]，每個都要 grep -r 確認全語料 0 筆命中。不能與這些題重複：{json.dumps(b['avoid'],ensure_ascii=False)}。上一題失敗原因：{b['problems']}
"""
    else:
        a,bb,d=M.COMP[comp]
        task=f"""
【你的任務】只針對「{comp}」（檔案 {a}_*.md、{bb}_補充_*.md、{d}_104職缺更新_*.md），重出 1 題 type="{b['type']}"（company="{comp}"）。原題失敗：{b['question']}，原因：{b['problems']}。請換一個主題與事實，答案的 quote 必須逐字存在於標題段落內。若是「職缺」題，gold 要列出所有符合的職缺（讀完整份 {d} 檔）。不能與這些題重複：{json.dumps(b['avoid'],ensure_ascii=False)}
"""
    pr=base+task+"\n輸出仍然是 JSON 陣列，只含 1 題。"
    pf=pathlib.Path(f"raw/rp_{i}.txt");pf.write_text(pr,encoding="utf-8")
    of=f"raw/ro_{i}.txt"
    procs.append(subprocess.Popen(['codex','exec','-s','read-only','--skip-git-repo-check','-C','C:/claude/aipe04期末/履歷/廠商深查','-o',of,'-'],stdin=open(pf,'rb'),stdout=open(f'raw/rl_{i}.txt','w'),stderr=subprocess.STDOUT,shell=True))
for p in procs: p.wait()
res=[]
for i,b in enumerate(bad):
    try: res.append(load(f"raw/ro_{i}.txt")[0])
    except Exception as e: res.append(None);print("fail",i,e)
json.dump(res,open("raw/regen_out.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)

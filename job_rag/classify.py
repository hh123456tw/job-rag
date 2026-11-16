"""輸出分類表（Markdown）：python -X utf8 -m job_rag.classify > 分類表.md
列出被排除的標題與段落數、公開段落的標題與段落數，以及各公司的公開段落數（「綜合」＝無法歸屬）。"""
from . import classification_table, public_company_counts

rows = classification_table()
for label, flag in (("被排除的段落（不進索引）", True), ("公開事實段落", False)):
    sub = [r for r in rows if r["excluded"] is flag]
    print(f"## {label}（{sum(r['count'] for r in sub)} 段）\n\n| 標題 | 段落數 |\n|---|---|")
    for r in sub:
        print(f"| {r['title']} | {r['count']} |")
    print()
print("## 公開段落：各公司段落數\n\n| 公司 | 段落數 |\n|---|---|")
for company, n in public_company_counts().items():
    print(f"| {company} | {n} |")

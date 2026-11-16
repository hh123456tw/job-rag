"""輸出分類表（Markdown）：python -X utf8 -m job_rag.classify > 分類表.md"""
from . import classification_table

rows = classification_table()
for label, flag in (("公開事實段落", False), ("私人段落", True)):
    sub = [r for r in rows if r["private"] is flag]
    print(f"## {label}（{sum(r['count'] for r in sub)} 段）\n\n| 標題 | 段落數 |\n|---|---|")
    for r in sub:
        print(f"| {r['title']} | {r['count']} |")
    print()

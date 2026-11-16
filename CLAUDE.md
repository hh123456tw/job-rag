# 求職情報問答

個人求職用的 RAG 問答工具。規格見 `SPEC.md`，名詞見 `GLOSSARY.md`。

## 規則
- 展示用索引只有公開事實段落：私人（排除）段落不進展示索引、不進 git、不進公開匯出與語料包、不出現在評估題與測試資料。分類不明的標題一律當私人。
- 自用資料只放本機 `selfdata/`（已被 `.gitignore` 擋住）；只有本人密碼通過後的自用模式才載入與查詢；展示模式不得因任何原因查到它。
- 完整語料與 `.env` 不進 git。
- 不憑空產生答案：查無、API 失敗都要明確回報，不回示範資料。
- 不 push、不開 PR，除非使用者說要做。
- 下載任何模型前先回報實際大小並等使用者同意。
- Python 輸出非 ASCII 文字時用 `python -X utf8`；檔案一律 utf-8。

## Agent skills

### Issue tracker

本機 markdown，放在 `.scratch/job-rag/`。See `docs/agents/issue-tracker.md`.

### Triage labels

預設五個標籤，本機以 `Status:` 行表示。See `docs/agents/triage-labels.md`.

### Domain docs

single-context。See `docs/agents/domain.md`.

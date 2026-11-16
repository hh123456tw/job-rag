# 求職情報問答

個人求職用的 RAG 問答工具。規格見 `SPEC.md`，名詞見 `GLOSSARY.md`。

## 規則
- 私人（排除）段落不進入這個專案：不索引、不送 LLM、不進 git、不出現在評估題與測試資料。分類不明的標題一律排除。只有公開事實段落進語料。
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

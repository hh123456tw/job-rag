# 09: 公開 repo 準備

**Blocked by:** 03, 05, 10, 15
**Status:** resolved

**What to build:** README、3 家範例語料（只含公開事實）、評估題。完整語料與 `.env` 已被 `.gitignore` 擋住。只用範例語料，另一台電腦能重現流程。

- [ ] 用範例語料從零重現流程的步驟寫在 README 並實測過一次
- [ ] repo 內找不到任何私人段落、金鑰或完整語料
- [ ] `SPEC.md`、`.scratch` 內容公開前先檢查是否含私人策略（不自動公開；使用者決定）

## 修正（2026-11-16）

- 不重寫私人 repo 的歷史，也不把私人 repo 改成公開。改為：用**白名單匯出**一個全新的乾淨資料夾 `dist/public_repo/`（預設拒絕，只複製明列的檔案），使用者要公開時另建一個新的 GitHub repo，從這個資料夾 `git init`。私人 repo 保持私人。
- 白名單不含：SPEC.md、GLOSSARY.md、CLAUDE.md、`.scratch/`、`docs/agents/`、`demo/`、`.env`、`models/`、`.cache/`、`dist/`、完整語料、含求職策略或履歷內容的任何文字。
- 匯出內容：程式、測試（只含假語料 fixtures）、啟動檔、公開版 README、`requirements`、3 家範例語料（只含公開事實段落，用現有載入流程過濾後重新寫成同格式的 md）、對應範例語料的範例評估題。

## Comments

- 完成（306 passed）。匯出 55 檔、約 275 KB 到 dist/public_repo；獨立掃描無金鑰、信箱、電話、個人名稱。UI 標題「求職情報問答」與公開 README 標題「公司調查問答」不一致，待決定。未驗：新 venv、模型下載指令。

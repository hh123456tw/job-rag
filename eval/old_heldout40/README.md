# 舊的 40 題獨立測試題（已被 100 題取代）

- 2026-11-17 起，獨立測試題改用 `eval/questions_heldout.json` 的 100 題（Codex CLI gpt-6.1-sol 出題，原稿與驗證在 `eval/gen100/`）。這個資料夾保留舊 40 題與當時的結果，只供對照，說明頁與文件不再引用。
- 為什麼換：舊 40 題與語料同一人（我）寫，語料換新版時其中 h40、r20 之類的題已不是「沒有答案」，要改標；新 100 題由另一個模型出，題型分開（單一公司、職缺清單、跨公司、不可回答），可以分題型看弱點。
- 檔案：`questions_heldout.json`（舊題檔）、`results_heldout*.{txt,json}`（舊檢索與生成結果）、`results_heldout_answers*.json`（舊答案）、`input_heldout.json`／`judge_gpt_heldout.json`（舊 GPT 複查）、`ragas_heldout_progress.json`（舊 RAGAS 逐題進度）。
- 這些舊結果是在補職稱清單之前的語料上量的，不能和新 100 題的數字混著比。

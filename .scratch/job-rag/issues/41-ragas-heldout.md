# 41: 獨立測試題的 RAGAS（現行設定）

**Blocked by:** 39（已合併）
**Status:** ready-for-agent

背景：現有 RAGAS 數字（忠實度 1.000、答案相關性、22 題）是 K=3 舊流程量的。現行設定是 K=5、補公司名、已指定公司門檻 0.62。票 39 已用現行設定對 40 題獨立測試題產生答案（`eval/results_heldout_answers.json`）。這張票只對這些**已存在的答案**跑 RAGAS，不重新生成。

## 做法
1. 先確認 `results_heldout_answers.json` 是否含 RAGAS 需要的 `question`、`answer`、`contexts`（實際送進 DeepSeek 的段落全文，含公司名與標題，沿用 `answer.format_source` 的格式）。若缺 contexts：用同一個 `/api/search` 重新取得當時的段落**不可行**（檢索可能變）；此時改為對題目重新呼叫主服務 `http://127.0.0.1:5000` 的 `/api/search` 與 `/api/answer`（本機直連免存取碼；真 DeepSeek ≤ 40 次，間隔 ≥ 1 秒）重新產生並**同時記錄** contexts，另存 `eval/results_heldout_answers_v2.json`，不覆蓋舊檔。
2. 沿用既有 RAGAS 流程（`eval/ragas_judge.py`、`job_rag/generation.py` 的評分函式、`.venv-ragas`、`requirements-ragas.txt`；評審 DeepSeek，`max_tokens=4096`）。只評**有答案且有給出答案**的題（沒答案題與答「查無」的題不打分，另列：被擋 n、查無 m）。
3. 輸出 `eval/results_heldout_generation.txt`／`.json`：每題 faithfulness、answer_relevancy、題數、平均與（若可）bootstrap 區間；逐題列出分數低於 0.9 的題與原因（讀答案與段落後簡述，不得美化）。
4. **跑法**：RAGAS 很吃資源且曾讓電腦當機。用獨立背景程序（PowerShell `Start-Process -WindowStyle Hidden`，輸出導到 `dist/logs/`），輪詢檔案進度，不要在前景長時間阻塞；先檢查可用記憶體（現有主服務與其他子代理各載一個 bge-m3，約 5GB 一個）；若 answer_relevancy 需要本機嵌入模型而記憶體不足，改為只報 faithfulness 並說明；不要自行下載模型（需要先回報大小等使用者同意）。
5. /about（簡報第 9 頁與長頁的答案評估段）與 `/threshold` 若有引用 RAGAS：新增「獨立題（現行設定）：忠實度 x（n 題）」與舊數字並列，舊數字維持「量測時為 K=3 設定」標註；數字取自輸出檔，缺檔就不寫。誠實註明：評審與生成同為 DeepSeek，可能偏樂觀。
6. 結果若低於舊數字，照實呈現。

## 不要做
- 不改檢索、門檻、提示詞、取段數；不重跑舊 30 題的生成與 GPT 複查；不碰 `selfdata/`、`.env`、ngrok；不停止或重啟 5000 埠服務；不得讓存取碼或密碼進入任何檔案。

## 驗收
- [ ] `eval/results_heldout_generation.*`；回報：評分題數、被擋／查無題數、平均、低分題與原因、DeepSeek 呼叫次數
- [ ] /about 與簡報頁新數字與輸出檔一致（有測試，缺檔略過）
- [ ] 全套 pytest 直接取結束碼；匯出掃描通過

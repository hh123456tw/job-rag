你是評審。任務：逐題判斷「答案」中的每一個事實陳述，是否有「段落」支持。

規則：
1. 只能用該題提供的段落當依據，不可使用外部知識或常識補充。
2. 把答案拆成獨立的事實陳述（每個陳述一件事；引用編號如 [1] 忽略，不算陳述）。
3. 每個陳述判斷 supported = true（段落明確寫出或可直接推得）或 false（段落沒寫、寫的不同、或把別家公司／別個職缺的內容算到這裡）。
4. 段落標題行 `[n] (公司 / 標題)` 是段落的一部分，公司名可用它確認。
5. supported = false 時，寫出簡短理由；supported = true 時，引用段落中的原句（20 字內）。
6. faithfulness = supported 為 true 的陳述數 ÷ 全部陳述數（0 到 1）。答案沒有任何事實陳述（例如只回「查無」）時填 null。

輸入：`input.json`，每題有 id、question、answer、passages。
輸出：只輸出一個 JSON 陣列，不要其他文字。每題一個物件：
{"id": "...", "claims": [{"text": "...", "supported": true, "evidence": "...或理由"}], "faithfulness": 0.0}

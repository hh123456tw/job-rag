# 求職情報問答

求職調查檔的問答工具。規格見 `SPEC.md`，名詞見 `GLOSSARY.md`。檢索方式有 5 種（票 03）：bm25、bge-small-zh、bge-m3、e5-large、hybrid。

## 跑法
```
pip install -r requirements.txt
set JOB_RAG_CORPUS=<語料資料夾>      # 完整語料不進 git
python -X utf8 app.py                # 開 http://localhost:5000
python -X utf8 -m job_rag.classify   # 分類表：被排除的標題與段落數、公開段落、各公司公開段落數
python -m pytest tests               # 用 tests/fixtures/mini 的假語料
```
載入語料時就丟掉排除段落，索引（BM25、向量、混合、快取）只有公開事實段落；沒有模式切換。分類不確定的標題一律排除。
跨公司的 104 檔（`補*`、`網址*`、`F_*` 等）依標題路徑歸公司；標題沒有公司時，檔名只含一家公司才採用，否則歸「綜合」。

## 問答頁按鈕（票 06）
- 11 家現場公司按鈕（再按一次取消；選了之後只查該公司）；4 顆常用問題：這家做什麼、有哪些職缺、用什麼技術、財務與新聞。句型與 `eval/questions.json` 一致（「X是做什麼的？」「X有哪些…？」「X的營收…」）。沒選公司就按常用問題，會提示先選公司。
- 公司按鈕對照語料的公司欄位，只有「尼諾思」對「尼諾思科技」；`JOB_RAG_REAL_CORPUS=<真語料> python -m pytest tests/test_buttons.py` 會核對。
- 2 顆查無示範取自不可回答題（u07、u06）。最高分低於門檻時顯示「可能沒有答案」，原文照樣顯示（淡色），不出現「整理成答案」、不呼叫 DeepSeek；門檻與預設檢索方式同 `job_rag`（見下面「查無門檻」）。
- 問句與評估題完全相同時，出現「看這題在評估裡的成績」，顯示該題名次與命中。

## 評估（票 02）
```
python -X utf8 -m job_rag.evalset --write-md   # 核對 30 題：引文在金標標題下、不可回答題的關鍵字搜不到；重寫 eval/questions.md
python -X utf8 -m job_rag.evaluate             # 對預設方式（bge-m3）評分；需 JOB_RAG_CORPUS
```
題目在 `eval/questions.json`（程式讀）與 `eval/questions.md`（人讀）。核對狀態一律是「待使用者確認」，只有使用者能改。
金標用「檔名＋標題路徑」；命中＝前 k 個結果中有段落在金標標題之下。正確拒答率見下面「查無門檻」。

## 向量檢索（票 03）
模型放 `models/`（不進 git），`search(..., method=...)` 全在本機跑，不連網。段落向量快取在 `.cache/`（不進 git），語料內容變了才重算。
```
python -X utf8 -m job_rag.evaluate --method all   # 5 種並列成績表，寫入 eval/results_methods.txt
python -m pytest tests                          # 假嵌入器，不需模型
set JOB_RAG_MODELS_TEST=1 && python -m pytest tests/test_vector.py   # 真模型冒煙，需 models/
```
混合 = BM25 + bge-m3，RRF（k=60，不調權重）。e5 自動加 `query: ` / `passage: ` 前綴。

## 預設檢索方式
預設是 bge-m3（`search()` 的預設值，介面也用它）。理由：在 25 題可回答題上 5 種方式中成績最好（見 `eval/results_methods.txt`）。

## 查無門檻（票 04）
- 做法：最高分低於門檻，就判為「可能沒有答案」。介面顯示明確文字，原文以淡色照列，沒有「整理成答案」按鈕。`search()` 本身仍回空串列。
- 門檻是 bge-m3 最高相似度 0.700（`retrieval.NOT_FOUND_THRESHOLD`）。混合用它的 bge-m3 最高分判斷；BM25、bge-small-zh、e5-large 分數尺度不同，沒做門檻。
- 挑法：試每個相鄰分數的中點，選「可回答題放行率＋不可回答題擋住率」最高的。
- 限制：門檻用評估的同一批 30 題挑，沒有獨立測試題，所以拒答率偏樂觀，只能當方向。可回答題被誤擋的比例見 `eval/results_methods.txt`。

## 信賴區間
題少（25 題），所以把題目重抽 1000 次（固定亂數種子 0），看 MRR 會落在哪個範圍。bge-m3 與混合的差，用同一批重抽的題目算；區間不含 0，才說差異可信。

## 「面試」行過濾
載入語料時，內文含「面試」二字的行整行丟掉（標題行不丟）。被丟的行數、範例與可能誤丟的公開內容寫在 `eval/results_methods.txt`；全部列出：`python -X utf8 -m job_rag.classify`。

## 整理成答案（DeepSeek）
```
copy .env.example .env               # 填入 DEEPSEEK_API_KEY；.env 不進 git
python -X utf8 smoke_deepseek.py "問題"   # 手動冒煙，會呼叫真 API
```
模型代號預設 `deepseek-flash`（官方文件：由 DeepSeek-V4.1-Flash-1017 提供），可用 `DEEPSEEK_MODEL` 覆寫。送出的只可能是 `search()` 回傳的公開事實段落；沒有原文結果時回「查無」，不呼叫 API。

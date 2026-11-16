# 求職情報問答

用公司調查筆記做的檢索問答（RAG，retrieval-augmented generation）範例，附網頁介面。每家公司一個對話頁，點預設題目或自己輸入問題；答案先出現並附出處，原文收在「看原文」。重點在「怎麼量」：5 種檢索方式用同一批題目比較，附信賴區間，也寫明這個評估的限制。

## 網頁有什麼

- **公司對話頁**：首頁列出語料裡的公司，點一家進入 `/c/<公司>`；另有「全部公司」做跨公司提問。每家各有一個對話框，記錄只存在你的瀏覽器。
- **預設題目**：每家公司 3 到 5 個可以直接點的問題（存在 `job_rag/company_presets.json`）。語料裡沒有預設的公司（例如範例語料的 3 家）改用最前面 3 個通用題。
- **「我能回答什麼」提示**：這家有哪些資料、沒有哪些資料，由載入的語料算出，不是寫死的。
- **追問記憶**：前端帶最近 2 輪對話；很短的追問（例如「那薪水呢？」）會依規則補上前一題的主題再檢索。伺服器不存對話，規則寫在 `job_rag/memory.py`，不用 LLM 改寫問句。
- **答案優先**：先顯示整理好的答案與出處，原文在「看原文」裡；沒有 JavaScript 時退回伺服器渲染的結果頁。
- **查無提示**：最高相似度低於門檻，就明說「我找不到很接近的內容，不確定有沒有答案」，原文淡色照列，不呼叫 LLM。
- **失敗不亂答**：沒有金鑰、逾時、API 錯誤、有每小時用量上限（`JOB_RAG_ANSWER_LIMIT`）都寫明原因，不補示範答案。
- **專案說明頁 `/about`**：白話說明做了什麼、怎麼量、哪裡不夠好；成績表與信賴區間讀自 `eval/results_methods.json`。

**English summary.** A small Retrieval-Augmented QA demo with a web UI, built on company-research notes (Traditional Chinese). Each company has its own chat page with preset questions, short follow-up memory, answer-first display with sources, and a "probably no answer" notice. It splits notes by heading, compares five retrieval methods (BM25, bge-small-zh, multilingual-e5-large, bge-m3, and BM25+bge-m3 with reciprocal rank fusion), refuses to answer when the best similarity is below a threshold, and reports Hit@1 / Hit@3 / MRR with bootstrap confidence intervals. Only a tiny sample corpus (3 companies, 32 passages) and 15 sample questions are included, so the numbers are a demonstration of the method, not a benchmark. Limitations: few questions, questions written against the same corpus, a threshold tuned on the same questions, and a judge model that may favor its own answers. The optional answer generation calls the DeepSeek API and needs your own key.

## 快速開始（Windows、Python 3.11）

```
pip install -r requirements.txt -r requirements-vector.txt
```

### 1. 取得模型（不會自動下載）

向量檢索用的模型放在 `models/`，程式只從本機讀，不連網。只想看 BM25 不需要任何模型。

| 檢索方式 | 模型 | 來源 | 大小（本機實際資料夾） |
|---|---|---|---|
| bge-m3（預設） | `models/bge-m3` | https://huggingface.co/BAAI/bge-m3 | 約 2.2 GB |
| bge-small-zh | `models/bge-small-zh-v1.5` | https://huggingface.co/BAAI/bge-small-zh-v1.5 | 約 92 MB |
| multilingual-e5 | `models/multilingual-e5-large` | https://huggingface.co/intfloat/multilingual-e5-large | 約 2.2 GB |

下載指令範例（需要先 `pip install huggingface_hub`；這幾行沒有在本機重跑過，模型是事先放好的，若指令有變請以官方文件為準）：

```
hf download BAAI/bge-m3 --local-dir models/bge-m3 --include "1_Pooling/*" --include "*.json" --include "pytorch_model.bin"
hf download BAAI/bge-small-zh-v1.5 --local-dir models/bge-small-zh-v1.5
hf download intfloat/multilingual-e5-large --local-dir models/multilingual-e5-large
```

預設只需要 bge-m3。要跑 5 種方式並列，才需要另外兩個。

### 2. 環境變數

| 變數 | 用途 | 預設 |
|---|---|---|
| `JOB_RAG_CORPUS` | 語料資料夾（遞迴讀 `*.md`） | 沒有預設，一定要設；範例是 `sample_corpus` |
| `JOB_RAG_MODELS` | 模型資料夾 | `models` |
| `JOB_RAG_CACHE` | 段落向量快取 | `.cache`（第一次編碼約幾分鐘，之後讀快取） |
| `JOB_RAG_PORT`、`JOB_RAG_HOST` | 網頁埠與監聽位址 | `5000`、`127.0.0.1` |
| `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` | 把檢索到的段落整理成答案；可放在 `.env`（見 `.env.example`） | 不設就沒有整理好的答案，只看得到原文 |

### 3. 用範例語料跑起來

```
set JOB_RAG_CORPUS=sample_corpus
set JOB_RAG_MODELS=models
python -X utf8 -m job_rag.classify                       :: 分類表：被排除的段落數、公開段落數、各公司段落數
python -X utf8 -m job_rag.evaluate --method bm25         :: 單一檢索方式的成績
python -X utf8 -m job_rag.evaluate --method bge-m3
python -X utf8 -m job_rag.evaluate --method all          :: 5 種並列，寫入 eval/results_methods.txt 與 .json
python -X utf8 app.py                                    :: 開 http://127.0.0.1:5000（首頁是公司清單，點一家進對話頁）
```

Windows 也可以雙擊 `start.bat`（預設語料是同資料夾的 `sample_corpus`、模型是 `models`；已設環境變數就用你設的）。`start.bat phone` 或 `start_phone.bat` 會對區網開放，方便用手機開同一個頁面。

網頁分兩部分：公司清單與每家公司的對話頁（`/c/<公司>`），以及 `/about`（成績表，數字讀自 `eval/results_methods.json`，要先跑上面的 `--method all`；沒有 DeepSeek 金鑰就沒有生成層評估，頁面會直接寫明）。啟動時會先載入模型，這段時間頁面顯示「準備中」。

### 4. 測試

```
python -X utf8 -m pytest tests
```

用 `tests/fixtures/mini` 的假語料與假嵌入器，不需要模型也不連網。少數測試要設環境變數才會跑（沒設就顯示 skipped）：`JOB_RAG_REAL_CORPUS`（對自己的完整語料做冒煙）、`JOB_RAG_REAL_QUESTIONS`（完整題組）、`JOB_RAG_MODELS_TEST=1`（用真模型）。

### 5. 整理成答案（選用，會呼叫外部 API）

```
copy .env.example .env            :: 填入自己的 DEEPSEEK_API_KEY
```

送出的只有檢索回來的段落，不會送整份語料。沒有金鑰、逾時、達用量上限或 API 回錯，頁面顯示原因，原文結果照常顯示，不補假答案。生成層評估（RAGAS）要另外裝套件並花 API 費用，做法見 `requirements-ragas.txt` 與 `python -X utf8 -m job_rag.generation --help`；這份範例沒有附生成層結果。

## 範例資料

- `sample_corpus/`：3 家公司（奧衍、尼諾思科技、遠振資訊）的公開事實，共 32 個段落（`python -X utf8 -m job_rag.classify` 會印出：被排除 0 段、公開 32 段）。內容整理自公開網頁與登記資料，每條都標明來源與【自述】【第三方】。
- `eval/questions.sample.json`：15 題，12 題可回答、3 題不可回答。每題有 `source` 欄位：5 題取自較大的題組（只改了金標檔名），其餘新增於範例語料。每題的金標引文都由程式核對過（`python -X utf8 -m job_rag.evalset` 的 `verify`），**但「核對狀態」仍是「待使用者確認」，沒有人逐題對照過原始網頁**。

## 設計重點

- **依標題切段，每段帶公司名與標題路徑。** 段落是檢索與評分的最小單位；索引文字前面加上「公司 標題路徑」，問句提到公司或主題時比較容易對上。
- **5 種檢索方式用同一批題目比較。** BM25（jieba 斷詞）、bge-small-zh、multilingual-e5、bge-m3、混合（BM25 加 bge-m3，用 RRF 合併名次，k=60，不調權重）。預設用 bge-m3。
- **只用公開事實。** 載入語料時就按標題白名單分類：標題不在白名單的段落一律排除，不進索引、不送 LLM（白名單在 `job_rag/retrieval.py` 的 `PUBLIC`，不確定的標題預設排除）。
- **查無門檻。** bge-m3 最高相似度低於 0.700 就顯示「可能沒有答案」，原文以淡色照列，也不呼叫 LLM。
- **失敗不亂答。** 沒有金鑰、API 失敗、模型缺檔都顯示明確錯誤，不回示範資料。
- **評估方法。** 金標用「檔名＋標題路徑」定義，命中＝前 k 個結果中有段落在金標標題之下；指標是 Hit@1、Hit@3、MRR；不可回答題另外看正確拒答率，不混入 MRR。
- **信賴區間。** 題少，所以把題目重抽 1000 次（可重複抽、固定亂數種子 0）取 95% 範圍；兩種方式的差用同一批重抽的題目算，區間含 0 就不說有差異。
- **可選功能。** 問句只含一家公司名時只搜那家（`JOB_RAG_DETECT=0` 關閉）；同公司同文字的段落合併（`JOB_RAG_DEDUPE=0` 關閉）；`python -X utf8 -m job_rag.export_bundle` 可匯出只含公開段落與預先算好向量的語料包。

## 範例語料上的成績

12 題可回答題，排名不套查無門檻，名次最多看到第 10。一次本機實測（`python -X utf8 -m job_rag.evaluate --method all`）：

| 檢索方式 | Hit@1 | Hit@3 | MRR（95% 區間） |
|---|---|---|---|
| BM25 | 0.333 | 0.750 | 0.595 [0.432, 0.762] |
| bge-small-zh | 0.250 | 0.750 | 0.558 [0.408, 0.708] |
| bge-m3 | 0.833 | 1.000 | 0.917 [0.792, 1.000] |
| multilingual-e5 | 0.750 | 0.917 | 0.854 [0.688, 0.958] |
| 混合（BM25＋bge-m3） | 0.750 | 1.000 | 0.861 [0.722, 1.000] |

bge-m3 減混合的 MRR 差是 +0.056，區間 [+0.000, +0.167] 含 0，不能說兩者有差異。查無門檻 0.700 在這份範例上擋住 2/3 題不可回答題，卻也誤擋 6/12 題可回答題（誤擋的題原文仍會顯示，只是淡色並提示「可能沒有答案」）。這個門檻是在另一個較大的語料上挑的，用在這 3 家的小語料上明顯偏嚴。

## 限制

- **題少。** 可回答題只有 12 題，區間很寬（見上表），名次差幾題就會變。只能當方向，不能當精確數字。
- **語料與題目同源。** 題目是對著同一份語料寫的，用詞容易和段落重疊，對 BM25 與向量檢索都偏有利；沒有獨立的測試題。
- **門檻用同批題挑。** 查無門檻 0.700 不是在這 15 題上獨立驗證的；上面的拒答與誤擋數字是用挑門檻的同類題目打分，偏樂觀；而且換到小語料後誤擋率很高。
- **評審偏好。** 生成層評估（如果你自己跑）由 DeepSeek 同時當生成模型與評審，同一個模型評自己寫的答案，分數可能偏高。
- **範例語料很小。** 3 家、32 段；公司數少，檢索時干擾段落也少，成績不能推到大語料。
- **只量檢索與「答案有沒有依據」。** 沒有量答案是否正確、是否完整。
- 範例語料內容整理自公開網頁，可能過期或有誤，請以原始來源為準。

## 換成自己的語料

1. 準備一個資料夾，裡面放 `*.md`（可有子資料夾）。一家公司一個檔案，檔名用 `S1_公司名.md`、`S2_公司名.md` 這種格式（或 `01_` 這種兩位數編號開頭），公司名取自檔名；放在子資料夾或檔名不是這種格式的檔案，公司由標題路徑決定（標題含已知公司名才歸屬，否則歸「綜合」）。
2. 用標題分段（`#`、`##`、`###`）。**只有標題在白名單內的段落會進索引**，白名單是 `job_rag/retrieval.py` 的 `PUBLIC`（基本資料、業務與財務、職缺、技術堆疊、近一年新聞等）；其他標題一律排除。換成自己的標題結構時，要改這一份清單，並用 `python -X utf8 -m job_rag.classify` 逐項檢查哪些被排除、哪些公開。
3. 設 `JOB_RAG_CORPUS=<你的資料夾>`，重跑 `classify`。向量快取以段落內容的雜湊為鍵，語料改了會自動重算。
4. 寫自己的題目，格式見 `eval/questions.sample.json`：可回答題要有金標（檔名、標題路徑、引文），不可回答題要列查過的關鍵字。用 `python -X utf8 -m job_rag.evalset` 核對（引文要真的在金標標題之下；不可回答題的關鍵字要真的搜不到）。
5. 重跑 `evaluate --method all`。放了 `eval/questions.json` 就優先用它，沒有才用 `eval/questions.sample.json`。
6. `app.py` 的公司按鈕在語料只含部分預設公司時，會改列語料裡有的公司；要固定自己的清單，改 `app.py` 的 `LIVE_COMPANIES`；預設題目由 `job_rag/company_presets.json` 提供，沒列在裡面的公司用通用題。
7. `job_rag/retrieval.py` 的 `EXCLUDED_COMPANIES` 是「整家公司不載入」的名單，只對 `sample_corpus/` 以外的語料生效。名單裡的名字剛好和你的公司重複時，清空或修改它。

## 目錄

```
app.py                  Flask 網頁（公司清單、對話頁、/about）
job_rag/                載入、分類、檢索、評估、生成層評估、對話記憶、預設題目、用量上限、說明頁
job_rag/company_presets.json  每家公司的預設題目
sample_corpus/          範例語料（3 家）
eval/questions.sample.json  範例評估題
tests/                  測試與假語料 fixtures
scripts/make_icons.py   產生加到主畫面用的圖示（只用 Pillow）
static/                 圖示
```

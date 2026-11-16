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

## 一鍵啟動、公司名過濾、去重（票 14）
Windows 雙擊 `start.bat`（或 `python -X utf8 app.py`）：啟動時先載入 bge-m3 與索引，載入完成前頁面顯示「準備中」並自動重新整理，完成後才可查詢；第一次查詢不再另外等載入。語料與模型路徑在 `start.bat` 開頭，可用環境變數 `JOB_RAG_CORPUS`、`JOB_RAG_MODELS` 覆寫。
- **公司名自動過濾**：問句整串含某一家公司的名稱或別名（`ALIASES`，如「台哥大」「神通」）時，只搜那一家；含兩家以上不過濾；介面上選了公司就以選的為準。只做完全比對，不猜子字串：「台灣」不等於「台灣大哥大」，「藍新金流」不在公司清單，所以不過濾。
- **結果去重**：同一公司、文字相同（全形轉半形、去空白後）的段落只留分數最高的一份，其他位置寫在「也出現於」。評分的命中判斷把「也出現於」算進去，金標在被合併的那份仍算命中。「整理成答案」的出處清單不重複。
- 兩個功能各有開關：環境變數 `JOB_RAG_DETECT=0`、`JOB_RAG_DEDUPE=0` 關掉介面上的功能；`search(..., detect=True, dedupe=True)` 與 `python -X utf8 -m job_rag.evaluate --detect --dedupe` 在程式與評分中開（預設關，原本的成績不變）。
- 各自對成績的影響（四種開關組合並列，含信賴區間）：`python -X utf8 -m job_rag.evaluate --toggles [--method bm25]`，結果在 `eval/results_toggles.txt`（bge-m3）與 `eval/results_toggles_bm25.txt`。規則沒有為了成績調整。

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
載入語料時，內文含「面試」二字的非表格行整行丟掉；表格列只清空含「面試」的欄位，保留職缺名稱、網址等其他欄位；第三方面試網站的列整行丟掉。標題行不丟。被丟的行數與範例寫在 `eval/results_methods.txt`，逐行判斷在 `eval/line_filter_review.md`；全部列出：`python -X utf8 -m job_rag.classify`。

## 整理成答案（DeepSeek）
```
copy .env.example .env               # 填入 DEEPSEEK_API_KEY；.env 不進 git
python -X utf8 smoke_deepseek.py "問題"   # 手動冒煙，會呼叫真 API
```
模型代號預設 `deepseek-flash`（官方文件：由 DeepSeek-V4.1-Flash-1017 提供），可用 `DEEPSEEK_MODEL` 覆寫。送出的只可能是 `search()` 回傳的公開事實段落；沒有原文結果時回「查無」，不呼叫 API。

## 生成層評估（票 11，RAGAS）
指標只有 2 個：faithfulness（忠實度：答案的每個陳述，段落裡找不找得到依據）、answer relevancy（答案相關性：從答案反推問題，和原問題像不像）。檢索固定用 `search()` 預設（bge-m3）。
流程：每題 `search()` → 被查無門檻擋住就記「被查無門檻擋住」、不呼叫 LLM → 否則用 `answer.py` 生成 → RAGAS 評審。送進生成與評審的只有檢索回來的公開事實段落。
- 25 題可回答題逐題有分數；平均只算「已評分」的題，評估失敗的題數與題號明列。被查無門檻擋住的可回答題沒有被打分，也不補預設分數，單獨列出。
- 5 題不可回答題只報「回查無」的比例（含被門檻擋住），不計入平均。
- API 失敗標「評估失敗」，不補分、不略過。

安裝（ragas 0.4.4 要求 `openai<2`，和主環境的 openai 3.x 衝突，所以裝在獨立 venv）：
```
python -m venv --system-site-packages .venv-ragas
.venv-ragas\Scripts\python -m pip install -r requirements-ragas.txt
```
接法：`AsyncOpenAI(base_url="https://api.deepseek.com")` → `ragas.llms.llm_factory(model, client=..., mode=instructor.Mode.JSON)`；DeepSeek 只支援 `json_object`，所以用 JSON 模式。嵌入模型用本機 bge-m3（`job_rag/ragas_judge.py`），不連網。評審模型與生成模型相同（`answer.py` 的設定）。

乾跑（不打 API，只用本機 bge-m3 檢索，結果寫 `eval/estimate_generation.txt`）：
```
set JOB_RAG_CORPUS=<語料資料夾>
set JOB_RAG_MODELS=<models 資料夾>
python -X utf8 -m job_rag.generation
```
正式執行（會呼叫 DeepSeek 並花錢；需要 `.env` 的金鑰）：
```
.venv-ragas\Scripts\python -X utf8 -m job_rag.generation --run
```
輸出：`eval/results_generation.txt`（逐題＋平均＋限制說明）、`eval/results_generation.json`（逐題原始資料）、`eval/review_sample.csv`（固定種子 0 抽 10 題，「是否忠於出處」欄由人工填）。

## 專案說明頁（票 05）
`/about`（主頁頂端「專案說明」連結）：給面試官 1–2 分鐘看的 6 塊說明。成績與失敗案例只讀 `eval/results_methods.json`（`python -X utf8 -m job_rag.evaluate --method all` 與 `results_methods.txt` 同次產生）、`eval/results_generation.json`、`eval/crossjudge/judge_gpt.json`，不手寫數字。輸出檔缺、讀不了或和 `eval/questions.json` 的題組對不上（指紋不同），該兩塊顯示錯誤。失敗案例的挑法見 `job_rag/about.py` 的 `_cases`。

## 手機現場展示（票 17）
筆電當伺服器、手機當螢幕。語料、模型與金鑰都留在筆電，不上傳。預設只監聽本機（`127.0.0.1`）；只有手機模式才對區網開放，且不做任何通道或轉發，不會開到公開網路。

**現場 5 步驟**
1. 手機開「個人熱點」。
2. 筆電連上這個熱點。
3. 雙擊 `start_phone.bat`，或在命令列執行 `start.bat phone`。啟動視窗會印出「手機請開：http://<IP>:5000」。
4. Windows 防火牆跳出視窗時，勾「私人網路」後按允許（只勾公用網路不夠）。
5. 手機瀏覽器輸入視窗印出的網址。載入模型與索引約幾分鐘，這段時間畫面顯示「準備中」並自動重新整理；變成查詢頁再開始用。

等同命令：`set JOB_RAG_HOST=0.0.0.0` 後執行 `python -X utf8 app.py`。筆電畫面上的主頁頁尾也會顯示一行手機網址（只在手機模式、且從筆電本機開的頁面才有；手機看不到）。

**IP 偵測**：`job_rag/netinfo.py` 排除 `127.*`、`169.254.*` 與常見虛擬網卡（VMware、VirtualBox、Hyper-V、WSL、Docker、藍牙、VPN 等）。剩下多個時全部列出，最可能的標「最可能」：私有網段優先、名稱像 Wi-Fi 優先、結尾 `.1` 的排後面。未知的虛擬網卡會被列為候選，請挑連到手機熱點的那個。

**常見問題**
- 手機打不開：多半是防火牆。第一次啟動沒勾「私人網路」，到 Windows 安全性 > 防火牆 > 允許應用程式，勾 Python 的私人網路；也確認筆電和手機在同一個熱點。
- IP 變動：每次重連熱點，筆電的 IP 可能不同。重連後關掉啟動視窗、重新雙擊啟動檔，用新印出的網址。
- 熱點省電中斷：關掉手機熱點的自動關閉與省電模式，展示期間手機保持亮屏、插電。
- 筆電睡眠：睡眠後連線會斷。電源選項設成接電時不睡眠，並關掉闔上螢幕就睡眠。
- 筆電沒有外部網路（例如熱點沒有行動網路）：原文結果照常顯示；按「整理成答案」會顯示「整理失敗：無法連到 DeepSeek（逾時或無網路）…」，原文結果不受影響。

**驗證紀錄**：用筆電自己的區網 IP 以 curl 測過：預熱期間回「準備中」且帶自動重新整理，載入完成後回查詢頁；從區網位址連來的頁面沒有手機網址那一行。斷網情境用測試替身驗證（`tests/test_phone.py`）。手機實機要自己測一次。

## 公開版語料包（票 18 預備）

只含公開事實段落（公司、檔名、標題路徑、文字）與 bge-m3 預先算好的向量，不含原始調查檔。

- 匯出：`python -X utf8 -m job_rag.export_bundle`（需要 `JOB_RAG_CORPUS` 與本機模型），輸出到 `dist/public_bundle/`（不進 git）。
- 使用：設 `JOB_RAG_BUNDLE=<資料夾>`，`search()` 改從語料包載入，不需要原始語料，也不重新編碼段落（查詢句仍用本機 bge-m3）。沒設時行為不變。
- 段落雜湊與向量檔、筆數對不上時會報錯。語料包模式只支援 `bm25`、`bge-m3`、`hybrid`。
- 免費雲端 CPU 的量測見 `eval/spaces_feasibility.md`（`python -X utf8 eval/measure_spaces.py`）。

## 加到主畫面（票 16，輕量 PWA）
`/manifest.webmanifest`、`static/icon-{180,192,512}.png`（`python scripts/make_icons.py` 重產，只用 Pillow）與三種畫面共用的 meta 標籤（`job_rag/ui.py` 的 `PWA_HEAD`）。加到主畫面後以 standalone 開啟。路徑都是根路徑，換網址不用改。
**不做 service worker、不做離線快取**：查詢需要後端，離線快取只會讓畫面顯示舊內容。
- http 區網 IP：iOS Safari 的「加到主畫面」可用，不需要 https；Android Chrome 的安裝提示（安裝為 App）需要 https，http 下最多是瀏覽器標示的主畫面捷徑，是否全螢幕未驗證。
- https（通道或雲端）：兩者都可用，Android 才有安裝選項。
- 依據：[Chrome 安裝條件](https://web.dev/articles/install-criteria)、[MDN](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)（安裝不需要 service worker；localhost 例外）。

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

## 移出的公司（票 23）
奧衍、尼諾思科技、醫宇宙因資料太少，移出系統。做法：`retrieval.EXCLUDED_COMPANIES`（語料的公司欄位）列出的公司，載入語料時整家略過（連同它們的「面試」行統計）；語料檔不刪、不改。因此它們不在索引、BM25、向量快取（段落清單變了，快取檔名的雜湊跟著變，舊向量不會被用）、公司清單與按鈕（`app.LIVE_COMPANIES`）、預設題目（`company_presets.json`）、公司名偵測別名、「我能回答什麼」提示、評估題與追問題裡；問句寫到這三家的名字也不會被偵測成一家公司。要把某家移回來，從名單拿掉、重跑評估即可。公開範例語料 `sample_corpus/`（獨立的示範資料）不受名單影響。評估題中 `eval/questions.json` 的 c01、s01、j07、j09 與追問題 f03、f06 因此換成別家公司的同類題（核對狀態「待使用者確認」）。

## 一鍵啟動、公司名過濾、去重（票 14）
Windows 雙擊 `start.bat`（或 `python -X utf8 app.py`）：啟動時先載入 bge-m3 與索引，載入完成前頁面顯示「準備中」並自動重新整理，完成後才可查詢；第一次查詢不再另外等載入。語料與模型路徑在 `start.bat` 開頭，可用環境變數 `JOB_RAG_CORPUS`、`JOB_RAG_MODELS` 覆寫。
- **公司名自動過濾**：問句整串含某一家公司的名稱或別名（`ALIASES`，如「台哥大」「神通」）時，只搜那一家；含兩家以上不過濾；介面上選了公司就以選的為準。只做完全比對，不猜子字串：「台灣」不等於「台灣大哥大」，「藍新金流」不在公司清單，所以不過濾。
- **結果去重**：同一公司、文字相同（全形轉半形、去空白後）的段落只留分數最高的一份，其他位置寫在「也出現於」。評分的命中判斷把「也出現於」算進去，金標在被合併的那份仍算命中。「整理成答案」的出處清單不重複。
- 兩個功能各有開關：環境變數 `JOB_RAG_DETECT=0`、`JOB_RAG_DEDUPE=0` 關掉介面上的功能；`search(..., detect=True, dedupe=True)` 與 `python -X utf8 -m job_rag.evaluate --detect --dedupe` 在程式與評分中開（預設關，原本的成績不變）。
- 各自對成績的影響（四種開關組合並列，含信賴區間）：`python -X utf8 -m job_rag.evaluate --toggles [--method bm25]`，結果在 `eval/results_toggles.txt`（bge-m3）與 `eval/results_toggles_bm25.txt`。規則沒有為了成績調整。

## 問答介面（票 06、票 21）
兩步到答案：首頁是公司清單（8 家現場公司＋「全部公司」），點一家公司進入那家的對話頁 `/c/<公司>`，點一個預設題目就送出。答案先出現，附出處；原文收在「看原文」。
- **對話頁**：每家公司各一個對話框，記錄存在瀏覽器的 sessionStorage（以公司為鍵，各家互不干擾；存取失敗就不存）。頂端「← 公司清單」、公司名、「？」鈕（隨時再看一次「我能回答什麼」）、「專案說明」；底部固定輸入列。
- **預設題目**：每家 3 到 5 個，存在 `job_rag/company_presets.json`，由 `scripts/gen_company_presets.py` 離線產生（需要語料與模型）。規則：候選題庫 8 題依固定優先序，對該公司實際 `search(gate=True)`，沒被查無門檻擋住、且第 1 名段落的標題含該題的關鍵字才留下，取前 5；少於 3 題就補到 3 題（先補沒被門檻擋住的）。「全部公司」的 4 題跨公司題用同樣方式驗證。門檻沒有調整。
- **「我能回答什麼」**：打招呼之後的提示，主題與筆數由載入的公開段落計算（`job_rag/topics.py`）：公司簡介、業務與財務、部門在做什麼、職缺資料（段數）、技術堆疊、近期新聞。沒有的資料也明列：薪資範圍（語料沒有「月薪／年薪／時薪」後面接阿拉伯數字才算有；「待遇面議」不算）、員工人數（有「員工」「員工人數」「規模」後面接數字才算有；徵才的「人數：6~10 人」不算）、以及專案本來就不收的一類。公開段落少於 20 段、又被補預設題的公司，會明說「公開資料較少」。
- **處理過程**：回答時助理泡泡逐行顯示真的步驟：「搜尋資料（範圍：…）」（送出 `/api/search`）→「找到 N 段：標題…」（收到結果才顯示）→「整理答案」（送出 `/api/answer`）→ 答案。原文先顯示的段落收在「看原文（N）」。
- **失敗與低分**：最高分低於門檻：不呼叫 DeepSeek、提示「我找不到很接近的內容，不確定有沒有答案」，原文淡色並展開。DeepSeek 失敗、逾時（40 秒）、無網路、達用量上限：寫明原因，原文自動展開，不出現假答案。
- **端點**：`GET /api/search?q=&company=`（立刻回段落與是否低分，不計用量）、`GET /api/answer?q=&company=`（也可用舊路徑 `/answer`；計入每小時用量）。兩者都在存取碼保護之內，403／429 回 JSON。
- **沒有 JS 的退路**：`/?company=X` 與 `/?q=...` 仍是伺服器渲染頁（對話頁的 `<noscript>` 也是這個版本）。結果頁原文展開，「整理成答案」是一個連結，按了才由伺服器呼叫 DeepSeek（`/?q=...&answer=1`，同樣計次）。有 JS 的結果頁（直接輸入網址時）也會自動載入答案。
- **開發用替身旗標**：環境變數 `JOB_RAG_FAKE_ANSWER` 設成 `ok`、`slow`（延遲 4 秒）或 `fail`，才會用模擬的 DeepSeek 回應；預設不設，`start*.bat` 與 `start_public.ps1` 都不會設，測試會檢查。只在開發與截圖驗證時用，並且仍要有 `DEEPSEEK_API_KEY` 變數（隨便填）。
- 排版：手機內文 17px，點擊區至少 48px，單欄、沒有橫向捲動，淺色深色都可讀；沿用同一份簡約樣式，沒有外部資源。
- 8 家現場公司：按鈕文字與語料的公司欄位相同（`app.LIVE_COMPANIES`）；`JOB_RAG_REAL_CORPUS=<真語料> python -m pytest tests/test_buttons.py` 會核對。沒有 JS 的公司頁仍有 4 顆常用問題（這家做什麼、有哪些職缺、用什麼技術、財務與新聞）；「用什麼技術」問「X的技術堆疊與開發工具有哪些？」，比較接近段落用語。
- 32 題（4 句型 x 8 家現場公司）逐題檢查與句型試跑在 `eval/button_check.md`（`python -X utf8 eval/button_check.py` 重跑）。仍有 8 題低於門檻 0.700、顯示「可能沒有答案」（聯合報 3、凱基證券 2 最多）；門檻沒有調整。
- 2 個查無示範（u07、u06）收在首頁底部的「查無示範」，連到伺服器渲染的結果頁。最高分低於門檻時顯示「可能沒有答案」，原文照樣顯示（淡色）、不呼叫 DeepSeek；門檻與預設檢索方式同 `job_rag`（見下面「查無門檻」）。
- 沒有 JS 的頁面：輸入框按 Enter（手機鍵盤「前往」）一律執行「查」，表單第一個提交按鈕是隱藏的「查」。
- 問句與評估題完全相同時，伺服器渲染的結果頁出現「看這題在評估裡的成績」。

## 對話記憶（票 22）
追問（例如「那薪水呢？」）要能被理解。**伺服器不存對話**：前端從該對話框取最近 2 輪（問題＋答案文字，記在該公司對話框自己的 sessionStorage 鍵底下，公司 A 的記錄不會送到公司 B），放在 `history` 參數（JSON）送給 `/api/search` 與 `/api/answer`（`/answer` 同）。
- **驗證與截斷**（`job_rag/memory.py` 的 `clean_history`）：參數原文超過 4000 字、不是 JSON、不是 `[{"q": 字串, "a": 字串}]`（任何一項型別不符）→ 回 400 與 JSON 錯誤「對話記錄…」，不檢索、不呼叫 DeepSeek、不計用量。合格時只留最後 2 輪，問題截到 200 字、答案截到 300 字，空白與換行壓成一個空格。
- **追問補全規則**（只寫在 `memory.expand`）：有上一題、問句去頭尾空白後 12 字以內、不含任何公司名或別名、不含主題詞（做什麼、職缺、技術、營收、財務、新聞、產品、AI 這個單字）→ 檢索與公司偵測用「上一題的問句＋空格＋這一題」。其餘照舊。只用上一題的問句，不用答案；不用 LLM 改寫。例：上一題「甲科技有哪些職缺？」，這題「那薪水呢？」→ 搜「甲科技有哪些職缺？ 那薪水呢？」；「有哪些職缺？」（自帶主題詞）與「乙資訊的薪水呢？」（有公司名）不補全。連續追問時只接上一題，不會把更早的題目全接上。
- **提示詞**（`job_rag/answer.py` 的 `SYSTEM`、`history_block`）：有先前對話時，使用者訊息最前面多一個「先前對話」區塊（最近 2 輪問與答），明說只用來理解「那」「它」指什麼、不是證據；事實只能來自編號段落。另有兩條修正（票 22 追加）：只陳述段落明確說公司「使用、採用、提供、具備」的事，段落寫「頁面」「介紹」「相關」「未說明關係」時不得當作公司已採用；不照抄研究筆記字眼（改成「資料中沒有提到」「（資料標註為推測）」「（公司自述）」）。測試只檢查送出的提示詞含這些規則文字（`tests/test_prompt_rules.py`）；真的模型行為要用真 DeepSeek 另外驗。
- 查無門檻、存取碼、每小時用量（每次答案請求計一次）、低分不呼叫 DeepSeek、私人段落不進索引，都不受影響。
- **追問題迷你評估**：`eval/followups.json`（10 題；「前一題＋追問」，金標＝檔名＋標題路徑，引文由 `job_rag.evalset.verify` 核對；狀態「待使用者確認」）。`python -X utf8 -m job_rag.followups` 核對後分別量「不補全」與「補全」的 Hit@3，寫入 `eval/results_followups.json`，`/about` 讀取（缺檔就不顯示這一小段；檔過期或壞掉只在那一小段顯示錯誤）。只量了檢索，沒有量多輪答案品質；題少只能當方向。

## 評估（票 02）
```
python -X utf8 -m job_rag.evalset --write-md   # 核對 30 題：引文在金標標題下、不可回答題的關鍵字搜不到；重寫 eval/questions.md
python -X utf8 -m job_rag.evaluate             # 對預設方式（bge-m3）評分；需 JOB_RAG_CORPUS
```
題目在 `eval/questions.json`（程式讀）與 `eval/questions.md`（人讀）。核對狀態一律是「待使用者確認」，只有使用者能改。
金標用「檔名＋標題路徑」；命中＝前 k 個結果中有段落在金標標題之下。正確拒答率見下面「查無門檻」。

獨立測試題 100 題：`eval/questions_heldout.json`（單一公司 56、職缺清單 16、跨公司 10、不可回答 18）。由 Codex CLI 的 gpt-6.1-sol 單一模型出題，金標未經人工確認（狀態一律「待使用者確認」）；出題與驗證過程見 `eval/gen100/README.md`。檢索評估 `python -X utf8 eval/run_heldout.py`，實跑答案 `eval/run_heldout_answers.py`，RAGAS `eval/run_heldout_ragas.py`；結果在 `eval/results_heldout*.{txt,json}`。舊的 40 題與舊結果留在 `eval/old_heldout40/`，不再引用。

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
- 限制：門檻用評估的同一批 30 題挑，所以拒答率偏樂觀，只能當方向。另有調完才測的 100 題獨立測試題（見上面「獨立測試題 100 題」），沒用來挑門檻。可回答題被誤擋的比例見 `eval/results_methods.txt`。
- 票 23 換掉 4 題可回答題後重挑：算出 0.7001，程式內仍用 0.700（沒改）。前後（同一個門檻 0.700）：不可回答題擋住 5/5 → 5/5；可回答題誤擋 5/25（c01、c06、s01、s11、j09）→ 3/25（c01、c06、s11）。誤擋變少是因為換掉的題裡，原本被擋的 s01、j09 換成沒被擋的題，不是門檻更準。
- 跨公司門檻 `CROSS_FLOOR` 2026-11-18 由 0.534 降到 0.50（使用者決定，只試算 25 題，沒有新題驗證）：100 題裡 10 題可回答的跨公司題，通過關鍵字檢查 3→6；舊 15 題可回答 11/12 不變。代價：舊 3 題沒答案的題檢索層不再擋住（0/3），靠答案層回「查無」或逐家寫「資料沒寫」（5 題實測沒有假答案）。
- hybrid 與 reranker 在獨立測試題上的比較（票 43、44，2026-11-18）：`python -X utf8 eval/run_heldout_methods.py`，結果在 `eval/results_heldout_methods.{txt,json}`。只算走一般檢索的可回答題 72 題。bge-m3 MRR 0.867；hybrid 0.798（差 -0.069，95% 區間 [-0.123, -0.026]，不含 0，比較差）；bge-m3 前 20 段＋bge-reranker-v2-m3 重排 0.910（差 +0.043，區間 [-0.012, +0.103]，含 0，不能說有差），CPU 每題約 7 秒。所以網站維持單獨 bge-m3，重排只存在評估程式。限制：候選段數只試 20；題目由單一模型出、金標未經人工確認；重排模型 `models/bge-reranker-v2-m3`（2.27 GB，不進 git，從 Hugging Face `BAAI/bge-reranker-v2-m3` 下載）。
- 跨公司路徑改用混合挑段（2026-11-18，使用者決定）：`cross_search` 每家的 3 段都用 BM25＋bge-m3 的 RRF 名次挑。查無判斷另看「這些公司全部段落的 bge-m3 最高分」（每段附的 `top`），不管那段有沒有被挑到，所以每題的最高分和 `CROSS_FLOOR` 的拒答行為逐題不變。舊跨公司題組每家取 1／2／3 段的涵蓋率 0.530／0.731／0.794 → 0.709／0.804／0.887，通過仍是 11/15；獨立題跨公司路徑通過 8/12 → 9/12，有答案 10 題取到的相關公司 20/44 → 36/44（「亞馬遜雲」那題 3 家變 2 家）。限制：評分是「段落有沒有出現關鍵字」，這個標準本身偏向 BM25；兩組題都已用來調過跨公司門檻，沒有新題驗證；沒有系統地用真 DeepSeek 量答案品質；React、MCP、Redis 三題仍被門檻擋住。一般檢索（單一公司、職缺清單）不變，仍是單獨 bge-m3。
- 分流改成看「在哪裡問」（2026-11-18，使用者決定）：公司頁內提問＝只搜那一家；全部公司頁，問句剛好提到一家公司＝只搜那一家；全部公司頁沒提公司名＝一律走跨公司（以前還要含「哪些公司」這類詞才走）。提到兩家以上公司仍走全部段落一起搜。跨公司詞表（`_CROSS_WORDS`）只剩一個用途：追問補全時，問句自己明講要看全部公司就不接上一題（`retrieval.asks_all`）。影響：全部公司頁裡沒有跨公司詞的問句，門檻由 0.70 變成 `CROSS_FLOOR`，沒答案的題更依賴答案層回「查無」；單一事實又沒講公司名的問句會變成逐家回答。限制：三組評估題（跨公司、真實問法、獨立題）裡沒有受這次改動影響的題，重跑後數字不變，所以這個改動沒有評估數字支持，只實際問了幾題。`eval/results_methods.txt` 的「未指定公司」那組（c01、c06）是檢索層的舊分法；這兩題含「哪一家公司」，在網站上本來就走跨公司。
- 提到兩家以上公司的問句（2026-11-18，使用者決定）：改走跨公司路徑，但只查問句提到的那幾家（仍限有按鈕的公司；每家取 `PER_COMPANY` 段，門檻 `CROSS_FLOOR`）。以前這種問句走全部段落一起搜、門檻 0.70，「台灣大哥大和聯合報誰的資本額高？」會被擋掉。現在三種情況：剛好提到一家（或在公司頁問）＝只搜那一家、門檻 0.62；沒提公司＝查全部現場公司；提到兩家以上＝只查那幾家。`/api/answer` 也和 `/api/search` 一樣先偵測「剛好一家」。預設設定下已沒有問句直接用到 0.70；`NOT_FOUND_THRESHOLD` 留著，因為 0.62 是用它減 `SCOPED_DROP` 算的（上一條說的「提到兩家以上仍走全部段落一起搜」已不成立）。限制：跨公司提示詞規定不排名、不說哪家最好，所以比較題只會列出各家的數字，不會直接說誰比較高；評估題裡沒有「提到兩家公司」的題，這個改動沒有評估數字支持，只實際問過幾題。
- 答案的引用編號檢查（2026-11-18）：`answer.bad_citations`。DeepSeek 的答案若引用了沒送給它的段落編號（例如只送 5 段卻寫 [7]），整個答案擋下，畫面顯示「整理失敗：答案引用了不存在的段落編號」，原文照常可看。只認 [1]～[99]；[2026] 這類四位數不算引用；沒有任何引用的答案不擋。限制：只查編號存不存在，不查那一段有沒有寫那句話；沒有自動重試。離線檢查已存的獨立題答案 70 則，沒有任何一則會被擋，所以這層目前是保險，不是常觸發的機制。
- RAGAS 換評審（2026-11-18，使用者決定）：`.venv-ragas/Scripts/python -X utf8 eval/run_ragas_gpt.py score --judge sonnet` 再 `report --judge sonnet`，結果在 `eval/results_ragas_sonnet.{txt,json}`。做法：本機開一個 OpenAI 相容的轉接（只聽 127.0.0.1），RAGAS 的提示詞原封不動交給指令列工具；評審是 Claude Sonnet 5.5（`claude -p --model claude-sonnet-5-5`，乾淨模式：不載入專案指示、掛鉤、工具，用登入的訂閱，不需要 API 金鑰）；嵌入仍用本機 bge-m3；答案與段落沿用 DeepSeek 評審那次的同一批，沒有重新生成。結果（91 題全部評完，沒有失敗）：30 題組 22 題忠實度 0.993、答案相關性 0.911（DeepSeek 評審時 0.995／0.918）；獨立測試題 69 題忠實度 0.982、答案相關性 0.824（DeepSeek 評審時 0.984／0.815）。忠實度低於 0.9 的有 4 題：s10、g018、g019、g092。另有一份 GPT 評審的結果（`--judge codex`，`eval/results_ragas_gpt.*`）：30 題組 22 題評完，獨立題因 Codex 用量上限只評到 47／69，沒有補分；說明頁優先用 Sonnet 那份。限制：評審只跑一次、輸出有隨機性；跨公司 11/18 改動之後的答案沒有重新生成也沒有重評；簡報版說明頁用這份結果，長版說明頁的 RAGAS 段落仍是 DeepSeek 評審那份；低分的 4 題沒有逐題看原因。
- 逐句複查也換 Sonnet 5.5（2026-11-18，使用者決定）：`python -X utf8 eval/crossjudge/run_judge.py judge sonnet`，規則仍是 `judge_prompt.md`，輸出 `eval/crossjudge/judge_sonnet_new.json`、`judge_sonnet_heldout.json`。結果：30 題組 22 題 114 個陳述中 113 個有依據；獨立測試題 69 題 212 個陳述中 206 個有依據；12 批都一次完成。陳述數比 GPT 那次少（GPT：293、304），因為兩個評審拆句的粗細不同，兩份的比例不能直接比。7 個不支持的陳述裡 5 個是「只有這幾個職缺」這類把話說滿的句子（段落沒有列全，答案卻說只有這些）。簡報版說明頁在 RAGAS 也是 Sonnet 評審時才用這份；長版說明頁仍用 GPT 那份。
- 簡報版說明頁的跨公司（2026-11-18）：跨公司只出現在「問全部公司」一頁，主數字是獨立測試題跨公司路徑有答案 10 題「該取到的公司，取到幾家」（加總，現在 36/44）；對照「只用 bge-m3 時 20/44」存在 `eval/results_cross_before_hybrid.json`（取自 commit d6c2f12 的輸出檔，分母對不上就不顯示）。Hit@k 在簡報版寫成「小數（題數）」，MRR 只寫小數，數數量的寫「幾個／幾個」。
- 跨公司的各家 MRR（2026-11-18）：`python -X utf8 eval/run_cross_mrr.py`，結果在 `eval/results_cross_mrr.{txt,json}`。跨公司題沒有唯一的金標段落，不能照一般檢索算 MRR；這裡的算法是「每一家該出現的公司，第一個含關鍵字的段落在那一家裡排第幾名」，取倒數後對 44 家次平均（每家只看前 10 名）。混合 0.680（排第 1 名 24/44、前 3 名內 36/44）；只用 bge-m3 0.406（13/44、20/44）。前 3 名內的家次與 `results_heldout.json` 的取到家數一致（程式自我檢查）。限制：字面比對偏向 BM25、換說法的題吃虧；這 10 題已用來調過門檻與挑段方式，偏樂觀；這個數字不能和一般檢索的 MRR 0.867 直接比。簡報版「問全部公司」頁兩個數字旁各放一個 MRR（混合 0.680、只用 bge-m3 0.406），算法寫在「怎麼測」第 5 步。

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
- 筆電沒有外部網路（例如熱點沒有行動網路）：原文結果照常顯示；答案卡會顯示「整理失敗：無法連到 DeepSeek（逾時或無網路）…」，原文自動展開，不受影響。

**驗證紀錄**：用筆電自己的區網 IP 以 curl 測過：預熱期間回「準備中」且帶自動重新整理，載入完成後回查詢頁；從區網位址連來的頁面沒有手機網址那一行。斷網情境用測試替身驗證（`tests/test_phone.py`）。手機實機要自己測一次。

## 公開網址（票 20，ngrok）
筆電當伺服器，ngrok 提供 https 網址，給面試官用手機看。網址在公網上，所以有存取碼與用量上限。

**啟動**：雙擊 `start_public.bat`（需要 ngrok 已安裝並設好帳號；批次檔不處理 authtoken）。它會：
1. 產生隨機存取碼（已設環境變數 `JOB_RAG_ACCESS_CODE` 就用它，至少 8 字元）。
2. 啟動 app，只監聽 `127.0.0.1`，不開區網。
3. 等模型與索引載入完成（最多約 15 分鐘），再啟動 ngrok。
4. 從 `http://127.0.0.1:4040/api/tunnels` 取得公開網址（最多等 30 秒），印出完整網址。

**網址格式**：`https://<ngrok 網址>/?k=<存取碼>`。第一次帶對碼會存成 cookie（HttpOnly、SameSite=Lax；https 下加 Secure），之後同一支手機不用再帶。沒帶或錯誤回 403。`/static/` 圖示與 `/manifest.webmanifest` 不需要碼（加到主畫面要用）。碼就在網址裡，只傳給要看的人。沒設 `JOB_RAG_ACCESS_CODE` 時（例如一般的 `start.bat`）行為完全不變。

**用量上限**：整理成答案（對話頁自動載入也算一次）全域每小時最多 100 次（`JOB_RAG_ANSWER_LIMIT` 可調；非正整數用預設）。超過時該次回 429，顯示上限與約幾分鐘後可再試；原文結果照常顯示，只看原文（`/api/search`）不計次。計數存在記憶體，重啟歸零。

**第一次開啟**：ngrok 免費版會先出現警告頁，手機點「Visit Site」。

**關閉**：關掉啟動視窗或按 Ctrl+C，app 與 ngrok 兩個行程都會結束。啟動時若 4040 埠已有別的 ngrok，會停止並提示先關掉它。

**風險**
- 網址在公網上，知道完整網址的人都能查；懷疑外流就關掉重開（每次重開換新碼與新網址）。
- 「整理成答案」會花你的 DeepSeek 額度；上限是全域的，一個人用完大家都不能用。
- 筆電要保持開機、不睡眠、有網路；關機或斷網網址就失效。

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

## 自用／展示切換（票 24）

預設是**展示模式**：只有公開事實段落，行為與以前完全相同。要查私人資料時才切到**自用模式**。

**設定（只寫變數名稱，值自己決定）**
- `JOB_RAG_OWNER_PIN`：本人密碼。沒設＝沒有自用模式，頁面沒有切換鈕，`/api/owner/*` 回 404。
- `JOB_RAG_SELF_DIR`：自用資料夾，預設專案根目錄的 `selfdata/`（已被 `.gitignore` 擋住）。沒有這個資料夾時，自用模式仍可用，只是只有語料裡被排除的私人段落。面經檔放在 `面經/**/*.jsonl`。

**怎麼用**：頁首有「展示｜自用」切換鈕。按「自用」會出現密碼欄，密碼用 POST 的 JSON body 送出，不會進網址。通過後頁面顯示橘色橫幅「自用模式：資料會送到 DeepSeek，請勿給別人看」。按「展示」立即切回，並清掉自用的對話記錄與畫面。

**機制**
- 模式只由伺服器簽名的 cookie 決定（`jr_owner`；HttpOnly、SameSite=Lax、https 時 Secure、效期 8 小時、簽章金鑰每次啟動隨機產生，重啟即失效）。查詢參數、history、直接呼叫 API 都不能切到自用；沒有有效 cookie 一律當展示。
- 密碼以 `hmac.compare_digest` 比對。錯誤次數全域計算（10 分鐘 5 次；通道後面的請求都來自 127.0.0.1，所以不用 IP），超過回 429，鎖定期間連正確密碼也不收。
- 兩個索引分開建：展示索引的程式路徑與向量快取檔名不變；自用索引的快取檔名多 `self_`（都在 `.cache/`）。啟動時（有設密碼）會在背景預先編碼自用索引；沒好之前，自用模式的請求回「準備中」，展示不受影響。
- 對話記錄（sessionStorage 的鍵）與 history 都帶模式。伺服器在展示模式只收標記為展示的輪次，沒標記或標記為自用的直接丟掉（不報錯）。
- 自用面經載入器：只收 `window_ok` 為真、未被鎖住、內文非空的篇；欄位缺、壞行一律略過。
- 自用模式的提示卡會寫出面經篇數與私人主題，並註明來源是自用資料；有面經的公司多兩個預設題。`python -X utf8 scripts/check_self_presets.py` 逐題驗證沒被查無門檻擋住。
- 查無門檻、每小時用量上限、存取碼、預熱頁、PWA 都不變。持有存取碼的人預設是展示；沒有本人密碼進不了自用。

## 公開版匯出（票 09）
```
set JOB_RAG_REAL_CORPUS=<完整語料>   # 有設才會逐字比對真語料檔名；真語料相關測試也靠它
python -X utf8 scripts/export_public_repo.py    # 輸出到 dist/public_repo/（不進 git）
```
預設拒絕：只複製 `scripts/export_public_repo.py` 的 `FILES`／`GLOBS` 明列的檔案；公開版 README、`start.bat`、`.gitignore` 來自 `public/`。匯出後自動掃描（金鑰、信箱、電話、私人路徑與帳號、私人用語、完整語料檔名、禁止的路徑），有發現就刪掉輸出並失敗。輸出資料夾沒有 git 歷史；要公開時另建新 repo，從該資料夾 `git init`。
範例語料在 `sample_corpus/`（3 家、只含公開事實段落），範例題在 `eval/questions.sample.json`（`source` 欄標明來源）。依賴完整題組或完整輸出的測試要設 `JOB_RAG_REAL_QUESTIONS=<eval/questions.json 的路徑>`、`JOB_RAG_REAL_CORPUS=<完整語料>` 才跑。

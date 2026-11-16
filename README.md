# 求職情報問答

求職調查檔的問答工具。規格見 `SPEC.md`，名詞見 `GLOSSARY.md`。目前只有 BM25 檢索。

## 跑法
```
pip install -r requirements.txt
set JOB_RAG_CORPUS=<語料資料夾>      # 完整語料不進 git
python -X utf8 app.py                # 開 http://localhost:5000
python -X utf8 -m job_rag.classify   # 輸出分類表（標題 x 公開/私人 x 段落數）
python -m pytest tests               # 用 tests/fixtures/mini 的假語料
```
預設是演示模式，只含公開事實段落。勾「查詢模式」才會含私人段落（橘色橫幅）。

## 評估（票 02）
```
python -X utf8 -m job_rag.evalset --write-md   # 核對 30 題：引文在金標標題下、不可回答題的關鍵字搜不到；重寫 eval/questions.md
python -X utf8 -m job_rag.evaluate             # 對 BM25 評分（演示模式／查詢模式分開）；需 JOB_RAG_CORPUS
```
題目在 `eval/questions.json`（程式讀）與 `eval/questions.md`（人讀）。核對狀態一律是「待使用者確認」，只有使用者能改。
金標用「檔名＋標題路徑」；命中＝前 k 個結果中有段落在金標標題之下。正確拒答率要等查無門檻（之後的票）才算，現在輸出「尚未實作門檻」。

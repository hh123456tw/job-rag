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

## 整理成答案（DeepSeek）
```
copy .env.example .env               # 填入 DEEPSEEK_API_KEY；.env 不進 git
python -X utf8 smoke_deepseek.py "問題"   # 手動冒煙，會呼叫真 API
```
模型代號預設 `deepseek-flash`（官方文件：由 DeepSeek-V4.1-Flash-1017 提供），可用 `DEEPSEEK_MODEL` 覆寫。只送公開事實段落；私人段落永不送出。

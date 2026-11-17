"""臨時伺服器（5140）：從主專案 .env 讀金鑰進環境變數（不印、不寫檔），再跑 app.py。"""
import os, runpy, sys
from pathlib import Path
for line in Path(r"C:\claude\aipe04期末\job-rag\.env").read_text(encoding="utf-8").splitlines():
    k, _, v = line.partition("=")
    if k.strip() == "DEEPSEEK_API_KEY":
        os.environ["DEEPSEEK_API_KEY"] = v.strip().strip("\"'")
os.environ.update(JOB_RAG_PORT="5140", JOB_RAG_HOST="127.0.0.1", JOB_RAG_LOCAL_OPEN="1")
sys.path.insert(0, os.getcwd())
sys.argv = ["app.py"]
runpy.run_path("app.py", run_name="__main__")

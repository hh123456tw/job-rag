"""量測免費雲端 CPU（2 vCPU）的可行性：python -X utf8 eval/measure_spaces.py
需要：已匯出的語料包（dist/public_bundle）、JOB_RAG_MODELS。不連網、不需要原始語料。
三項：load（載入 bge-m3）、query（預熱後 20 次查詢）、cold（啟動 app.py 到第一次可查詢）。
每項在新的行程裡跑，限制 2 個執行緒（OMP_NUM_THREADS=2、torch.set_num_threads(2)）並把行程綁在 2 個邏輯核心（環境變數 SPACES_AFFINITY 可改遮罩）。"""
import ctypes
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "dist" / "public_bundle"
PORT = 5077


class _Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def peak_mb(pid: int | None = None) -> float:
    """行程的工作集峰值（MB）。Windows 專用。"""
    k, p = ctypes.windll.kernel32, ctypes.windll.psapi
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x0400 | 0x0010, False, pid or os.getpid())  # QUERY_INFORMATION | VM_READ
    c = _Counters()
    c.cb = ctypes.sizeof(c)
    p.GetProcessMemoryInfo(wintypes.HANDLE(h), ctypes.byref(c), c.cb)
    k.CloseHandle(wintypes.HANDLE(h))
    return c.PeakWorkingSetSize / 1e6


def pin_two_cores(pid: int) -> None:
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x0200 | 0x0400, False, pid)  # SET_INFORMATION | QUERY_INFORMATION
    k.SetProcessAffinityMask(wintypes.HANDLE(h), ctypes.c_size_t(int(os.environ.get("SPACES_AFFINITY", "3"), 0)))  # 預設核心 0、1；可設 0x30000 等
    k.CloseHandle(wintypes.HANDLE(h))


def env() -> dict:
    e = {k: v for k, v in os.environ.items() if k not in ("JOB_RAG_CORPUS", "JOB_RAG_CACHE")}
    e |= {"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "JOB_RAG_BUNDLE": str(BUNDLE), "PYTHONUTF8": "1",
          "PYTHONPATH": str(ROOT)}
    return e


def questions() -> list[str]:
    qs = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]
    return [q["question"] for q in qs][:20]


# ---- 子行程 ----
def child_load():
    t0 = time.perf_counter()
    import torch
    torch.set_num_threads(2)
    from job_rag import retrieval
    t1 = time.perf_counter()
    m = retrieval._load_model("bge-m3")
    t2 = time.perf_counter()
    m.encode(["預熱"])
    t3 = time.perf_counter()
    print(json.dumps({"threads": torch.get_num_threads(), "import_s": t1 - t0, "load_s": t2 - t1,
                      "first_encode_s": t3 - t2, "peak_mb": peak_mb()}))


def child_query():
    import torch
    torch.set_num_threads(2)
    from job_rag import search
    t0 = time.perf_counter()
    search("預熱", gate=False)  # 讀語料包、載入模型、建索引、編碼一次查詢
    warm = time.perf_counter() - t0
    out = {"threads": torch.get_num_threads(), "warmup_s": warm}
    for method in ("bge-m3", "hybrid"):
        ts = []
        for q in questions():
            t = time.perf_counter()
            search(q, method=method, gate=False)
            ts.append(time.perf_counter() - t)
        out[method] = {"n": len(ts), "median_s": statistics.median(ts), "max_s": max(ts), "min_s": min(ts)}
    out["peak_mb"] = peak_mb()
    print(json.dumps(out))


# ---- 主程式 ----
def run_child(mode: str) -> dict:
    p = subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()), mode], env=env(), cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    pin_two_cores(p.pid)
    out, _ = p.communicate()
    return json.loads(out.strip().splitlines()[-1])


def get(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=60) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except OSError:
        return 0, ""


def cold() -> dict:
    e = env() | {"JOB_RAG_PORT": str(PORT), "JOB_RAG_CACHE": tempfile.mkdtemp()}
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, "-X", "utf8", "app.py"], env=e, cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pin_two_cores(p.pid)
    try:
        q = "/?q=" + urllib.parse.quote("台灣大哥大有哪些職缺？")
        while True:
            code, body = get(q)
            if code == 200 and "準備中" not in body:
                break
            if p.poll() is not None or time.perf_counter() - t0 > 600:
                raise RuntimeError("app.py 沒有在 10 分鐘內可查詢")
            time.sleep(0.25)
        cold_s = time.perf_counter() - t0
        t = time.perf_counter()
        code, body = get(q)
        return {"cold_start_s": cold_s, "first_page_query_s": time.perf_counter() - t, "status": code,
                "has_hits": "class='hit" in body, "peak_mb": peak_mb(p.pid)}
    finally:
        p.kill()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        {"load": child_load, "query": child_query}[sys.argv[1]]()
    else:
        if not BUNDLE.is_dir():
            sys.exit("先執行：python -X utf8 -m job_rag.export_bundle")
        res = {"cpu": os.environ.get("PROCESSOR_IDENTIFIER", ""), "logical_cores": os.cpu_count(),
               "load": run_child("load"), "query": run_child("query"), "cold": cold()}
        print(json.dumps(res, ensure_ascii=False, indent=1))

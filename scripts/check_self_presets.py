"""驗證自用模式的面經預設題（票 24）：python -X utf8 scripts/check_self_presets.py

需要 JOB_RAG_CORPUS、JOB_RAG_MODELS，以及有面經的 JOB_RAG_SELF_DIR（沒設就用 selfdata/）。不呼叫任何 LLM。
每個面經預設題用 search(gate=True, mode="self") 檢查：沒有被查無門檻擋住，且前 3 名至少有一段是自用資料（面經或私人筆記）。
只印通過與否和篇數，不印任何面經內容。有題沒過就以非 0 結束。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app  # noqa: E402
from job_rag import search  # noqa: E402
from job_rag.retrieval import NOT_FOUND_THRESHOLD  # noqa: E402


def main() -> int:
    bad = total = 0
    rows = [(label, name) for label, name in app._company_buttons("self")] + [(app.ALL, "")]
    print(f"查無門檻 {NOT_FOUND_THRESHOLD}")
    for label, name in rows:
        for key, _, q in app._presets(label, "self", name):
            if not key.startswith("iv-"):
                continue
            total += 1
            hits = search(q, company=name or None, mode="self")  # gate=True（預設）
            top3 = hits[:3]
            n_iv = sum(h.get("file") == "面經" for h in top3)
            ok = bool(hits) and any(h.get("private") for h in top3)
            bad += not ok
            print(f"{'通過' if ok else '未過'}  {label}／{key}：前 3 名 {len(top3)} 段，其中面經 {n_iv} 段、自用資料 {sum(bool(h.get('private')) for h in top3)} 段，最高分 {hits[0]['score']:.3f}" if hits
                  else f"未過  {label}／{key}：被查無門檻擋住")
    print(f"\n{total - bad}/{total} 題通過")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

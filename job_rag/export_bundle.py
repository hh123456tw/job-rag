"""匯出公開版語料包：python -X utf8 -m job_rag.export_bundle [輸出資料夾，預設 dist/public_bundle]
只含公開事實段落（公司、檔名、標題路徑、文字）與 bge-m3 預先算好的向量。需要 JOB_RAG_CORPUS 與本機模型。
用法：設環境變數 JOB_RAG_BUNDLE=<資料夾>，search() 就改從語料包載入。"""
import json
import sys
from pathlib import Path

import numpy as np

from . import retrieval as r


def export_bundle(corpus, out) -> dict:
    root = r._root(corpus) if corpus else r._root()
    segs = r._public(root)
    vecs = r._passage_vectors(root, "bge-m3")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "segments.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for s in segs:
            f.write(json.dumps({k: s[k] for k in ("company", "file", "heading_path", "text")}, ensure_ascii=False) + "\n")
    np.savez(out / "vectors.npz", vectors=vecs, segments_sha1=np.array(r.segments_hash(s["_index"] for s in segs)))
    return {"segments": len(segs), "dim": int(vecs.shape[1])}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dist/public_bundle"
    info = export_bundle(None, out)
    size = sum(f.stat().st_size for f in Path(out).iterdir())
    print(f"已匯出 {info['segments']} 段、{info['dim']} 維到 {out}（{size / 1e6:.2f} MB）")

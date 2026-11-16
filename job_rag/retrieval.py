"""語料 -> 段落 -> 分類 -> BM25 檢索。對外只有 search（與分類表）。"""
import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

# 公開事實：標題（去編號、去無害括號、去空白後）完全相同才算。其餘一律私人。
PUBLIC = {
    "基本資料", "基本資料與身分確認", "基本資料與法人關係", "業務與財務",
    "報名部門在做什麼", "報名部門：新興應用部", "智能應用發展部在做什麼", "數據發展部在做什麼",
    "專案辦公室在做什麼", "「Ai部」做什麼", "HR對應的職缺類型",
    "職缺", "技術堆疊", "近一年新聞",
    # 104 職缺檔：公司區塊與職缺清單
    "台灣大哥大", "凱基證券", "聯合報系", "叡揚資訊", "藍新資訊", "中華網龍", "艾普特", "華電聯網",
    "神通資訊科技", "神通資訊科技股份有限公司", "典凡科技", "典凡科技股份有限公司",
    "遠振資訊股份有限公司", "華電聯網股份有限公司", "艾普特媒體有限公司",
    "醫宇宙遠距健康科技股份有限公司", "奧衍股份有限公司", "數據立諮詢顧問", "數據立諮詢顧問有限公司",
    "宏碁雲架構服務", "宏碁雲架構服務股份有限公司", "尼諾思智慧科技股份有限公司",
    "目前開放職缺", "相關職缺", "AI／Python／後端／資料／全端相關職缺",
    "全部8頁列表中的AI／Python／後端／資料／軟體／全端／平台／雲端相關職缺",
    "軟體／AI／資料／雲端相關職缺", "使用者指定的4筆缺口", "只讀列表、未開內頁",
    "D666詳細",
    # 測試用假語料的 104 公司區塊
    "甲科技股份有限公司",
}
# 即使在公開區段之下，這些子標題仍是判斷，歸私人。
PRIVATE_SUB = {"候選評估", "典凡小結", "叡揚補充", "藍新資訊補充"}
# 括號內有這些字時不剝括號（括號可能在說「這是判斷」）。
_PRIVATE_WORDS = re.compile("風險|判斷|評價|面試|推測|矛盾|不一致|限制|未查到|對應|作戰|不要")
ALIASES = {"台哥大": "台灣大哥大", "聯合報系": "聯合報", "網龍": "中華網龍", "宏碁雲": "宏碁雲架構", "尼諾思": "尼諾思科技"}
GENERAL = "綜合"
_HEAD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_NUM = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[一二三四五六七八九十]+、|\([a-z]\))\s*")
_PAREN = re.compile(r"[（(][^）)]*[）)]")
CHUNK, OVERLAP = 600, 90


def _norm(title: str) -> str:
    t = _NUM.sub("", title.strip())
    t = _PAREN.sub(lambda m: m.group(0) if _PRIVATE_WORDS.search(m.group(0)) else "", t)
    return re.sub(r"\s+", "", t)


def _is_private(path: list[str]) -> bool:
    """path 不含 H1。未知標題、空路徑都是私人。"""
    norms = [_norm(t) for t in path]
    if not norms or any(n in PRIVATE_SUB for n in norms[1:]):
        return True
    return norms[0] not in PUBLIC


def _pieces(text: str):
    step = CHUNK - OVERLAP
    for i in range(0, max(len(text) - OVERLAP, 1), step):
        yield text[i:i + CHUNK]


def _corpus_dir(corpus) -> Path:
    p = corpus or os.environ.get("JOB_RAG_CORPUS")
    if not p:
        raise RuntimeError("未設定語料路徑：請設環境變數 JOB_RAG_CORPUS")
    p = Path(p)
    if not p.is_dir():
        raise RuntimeError(f"語料路徑不存在：{p}（JOB_RAG_CORPUS）")
    return p


def _company_of(path: list[str], names: list[str]) -> str:
    pairs = [*ALIASES.items(), *((n, n) for n in names)]
    for t in path:
        for alias, name in pairs:
            if alias in t:
                return name
    return GENERAL


@lru_cache(maxsize=4)
def _segments(root: str) -> tuple:
    root_p = Path(root)
    files = sorted(root_p.rglob("*.md"))
    deep = lambda f: f.parent == root_p and re.match(r"^(0[1-9]|1[0-6])_", f.name)
    names = [re.sub(r"^\d+_", "", f.stem) for f in files if deep(f)]
    segs = []
    for f in files:
        file_company = re.sub(r"^\d+_", "", f.stem) if deep(f) else None
        stack: list[tuple[int, str]] = []  # (level, title)，含 H1
        body: list[str] = []

        def flush():
            text = "\n".join(body).strip()
            body.clear()
            if not text:
                return
            path = [t for lv, t in stack if lv > 1]
            company = file_company or _company_of([*path, f.stem], names)
            head = " > ".join(path) or (stack[0][1] if stack else f.stem)
            for piece in _pieces(text):
                segs.append({
                    "company": company, "file": f.name, "heading_path": head, "private": _is_private(path),
                    "text": piece, "_index": f"{company} {head}\n{piece}",
                    "_title": " > ".join(_norm(t) for t in path) or "(標題前言)",
                })

        for line in f.read_text(encoding="utf-8").splitlines():
            m = _HEAD.match(line)
            if m:
                flush()
                lv = len(m.group(1))
                while stack and stack[-1][0] >= lv:
                    stack.pop()
                stack.append((lv, m.group(2)))
            else:
                body.append(line)
        flush()
    return tuple(segs)


def _tok(s: str) -> list[str]:
    return [t.lower() for t in jieba.cut_for_search(s) if re.search(r"\w", t)]


@lru_cache(maxsize=8)
def _bm25(root: str, mode: str):
    pool = [s for s in _segments(root) if mode == "query" or not s["private"]]
    return pool, (BM25Okapi([_tok(s["_index"]) for s in pool]) if pool else None)


METHODS = ("bm25", "bge-small-zh", "bge-m3", "e5-large", "hybrid")
# 方式 -> (models/ 下的資料夾, 查詢前綴, 段落前綴)
MODELS = {
    "bge-small-zh": ("bge-small-zh-v1.5", "", ""),
    "bge-m3": ("bge-m3", "", ""),
    "e5-large": ("multilingual-e5-large", "query: ", "passage: "),
}
RRF_K = 60


def rrf(rankings: list[list], k: int = RRF_K) -> list[tuple]:
    """Reciprocal Rank Fusion：每個名單中名次 r 的項目得 1/(k+r)，加總後由高到低。"""
    score: dict = {}
    for ranking in rankings:
        for r, item in enumerate(ranking, 1):
            score[item] = score.get(item, 0.0) + 1.0 / (k + r)
    return sorted(score.items(), key=lambda kv: (-kv[1], str(kv[0])))


@lru_cache(maxsize=3)
def _load_model(method: str):
    """只從本機 models/ 載入，不連網。"""
    from sentence_transformers import SentenceTransformer
    root = Path(os.environ.get("JOB_RAG_MODELS", "models"))
    path = root / MODELS[method][0]
    if not path.is_dir():
        raise RuntimeError(f"找不到模型：{path}（需先下載）")
    return SentenceTransformer(str(path), device="cpu", local_files_only=True)


def _encode(method: str, texts: list[str], is_query: bool) -> np.ndarray:
    _, qp, pp = MODELS[method]
    prefix = qp if is_query else pp
    v = np.asarray(_load_model(method).encode([prefix + t for t in texts], batch_size=16), dtype="float32")
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def _passage_vectors(root: str, method: str) -> np.ndarray:
    """全部段落（含私人，依 _segments 順序）的向量。磁碟快取，內容雜湊變了才重算。"""
    segs = _segments(root)
    h = hashlib.sha1("\x00".join(s["_index"] for s in segs).encode("utf-8")).hexdigest()[:16]
    f = Path(os.environ.get("JOB_RAG_CACHE", ".cache")) / f"{method}_{h}.npy"
    if f.is_file():
        return np.load(f)
    v = _encode(method, [s["_index"] for s in segs], is_query=False)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.save(f, v)
    return v


@lru_cache(maxsize=8)
def _index(root: str, method: str, mode: str):
    """(候選池, FAISS 內積索引)。演示模式的池在這裡就剔掉私人段落。"""
    import faiss
    segs = _segments(root)
    keep = [i for i, s in enumerate(segs) if mode == "query" or not s["private"]]
    pool = [segs[i] for i in keep]
    if not pool:
        return pool, None
    vecs = _passage_vectors(root, method)[keep]
    idx = faiss.IndexFlatIP(vecs.shape[1])
    idx.add(np.ascontiguousarray(vecs))
    return pool, idx


def _rank_bm25(root, question, mode, company):
    pool, bm = _bm25(root, mode)
    if not pool:
        return pool, []
    scores = bm.get_scores(_tok(question))
    order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
    return pool, [(i, float(scores[i])) for i in order if scores[i] > 0 and (not company or pool[i]["company"] == company)]


def _rank_vector(root, method, question, mode, company):
    pool, idx = _index(root, method, mode)
    if not pool:
        return pool, []
    sims, ids = idx.search(_encode(method, [question], is_query=True), len(pool))
    return pool, [(int(i), float(s)) for s, i in zip(sims[0], ids[0]) if not company or pool[i]["company"] == company]


def search(question: str, method: str = "bm25", mode: str = "demo", company: str | None = None,
           k: int = 3, corpus=None) -> list[dict]:
    """排序後的段落。模式與公司過濾在排名前做：演示模式的候選池根本不含私人段落。"""
    if method not in METHODS:
        raise ValueError(f"未支援的檢索方式：{method}")
    if mode not in ("demo", "query"):
        raise ValueError(f"未知模式：{mode}")
    root = str(_corpus_dir(corpus).resolve())
    if method == "bm25":
        pool, ranked = _rank_bm25(root, question, mode, company)
    elif method == "hybrid":
        pool, rb = _rank_bm25(root, question, mode, company)
        _, rv = _rank_vector(root, "bge-m3", question, mode, company)
        ranked = rrf([[i for i, _ in rb], [i for i, _ in rv]])
    else:
        pool, ranked = _rank_vector(root, method, question, mode, company)
    return [{key: pool[i][key] for key in ("company", "file", "heading_path", "private", "text")} | {"score": float(sc)}
            for i, sc in ranked[:k]]


def classification_table(corpus=None) -> list[dict]:
    """標題 × 公開／私人 × 段落數，給人檢查分類。"""
    counts: dict[tuple[str, bool], int] = {}
    for s in _segments(str(_corpus_dir(corpus).resolve())):
        key = (s["_title"], s["private"])
        counts[key] = counts.get(key, 0) + 1
    return [{"title": t, "private": p, "count": n} for (t, p), n in sorted(counts.items(), key=lambda kv: (kv[0][1], kv[0][0]))]

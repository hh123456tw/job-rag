"""語料 -> 段落 -> 分類 -> 丟掉排除段落 -> 檢索。對外只有 search（與分類表）。索引裡只有公開事實段落。"""
import hashlib
import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

# 公開事實：標題（去編號、去無害括號、去空白後）完全相同才算。其餘一律排除。
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
# 即使在公開區段之下，這些子標題仍是判斷，歸排除。
EXCLUDED_SUB = {"候選評估", "典凡小結", "叡揚補充", "藍新資訊補充"}
# 括號內有這些字時不剝括號（括號可能在說「這是判斷」）。
NOT_COLLECTED = "面試與評價"  # 對話頁「沒有的資料」要用的白話說法；這類段落一律不收（字眼只准放在這個檔，見 scripts/export_public_repo.py）
_EXCLUDED_WORDS = re.compile("風險|判斷|評價|面試|推測|矛盾|不一致|限制|未查到|對應|作戰|不要")
ALIASES = {"台哥大": "台灣大哥大", "聯合報系": "聯合報", "網龍": "中華網龍", "宏碁雲": "宏碁雲架構", "尼諾思": "尼諾思科技",
           "神通": "神通資訊", "華電": "華電聯網"}  # 檔名簡稱（補2_神通、補3_華電）
GENERAL = "綜合"
# 移出名單（票 23）：這些公司（語料的公司欄位）載入時整家略過，不進索引、向量快取、清單、偵測。研究筆記檔不動、不刪。
# 公開範例語料（sample_corpus/）是獨立的示範資料，不受名單影響。
EXCLUDED_COMPANIES = frozenset({"奧衍", "尼諾思科技", "醫宇宙"})
SAMPLE_CORPUS = Path(__file__).resolve().parent.parent / "sample_corpus"
_HEAD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_NUM = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[一二三四五六七八九十]+、|\([a-z]\))\s*")
_PAREN = re.compile(r"[（(][^）)]*[）)]")
CHUNK, OVERLAP = 600, 90


def _norm(title: str) -> str:
    t = _NUM.sub("", title.strip())
    t = _PAREN.sub(lambda m: m.group(0) if _EXCLUDED_WORDS.search(m.group(0)) else "", t)
    return re.sub(r"\s+", "", t)


def _is_excluded(path: list[str]) -> bool:
    """path 不含 H1。未知標題、空路徑都是排除。"""
    norms = [_norm(t) for t in path]
    if not norms or any(n in EXCLUDED_SUB for n in norms[1:]):
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


BUNDLE_PREFIX = "bundle:"


SELF_PREFIX, SELF_SEP = "self:", "\x00"
MODES = ("demo", "self")  # 展示（預設）、自用。伺服器只在本人 cookie 有效時才會傳 self


def _root(corpus=None, mode: str = "demo") -> str:
    """索引的鍵。沒傳 corpus 且設了 JOB_RAG_BUNDLE 時用語料包，否則用原始語料。自用模式的鍵另加前綴與自用資料夾，兩個索引不共用任何快取。"""
    if mode not in MODES:
        raise ValueError(f"未支援的模式：{mode!r}")
    b = None if corpus else os.environ.get("JOB_RAG_BUNDLE")
    if not b:
        key = str(_corpus_dir(corpus).resolve())
    elif not Path(b).is_dir():
        raise RuntimeError(f"語料包路徑不存在：{b}（JOB_RAG_BUNDLE）")
    else:
        key = BUNDLE_PREFIX + str(Path(b).resolve())
    if mode == "demo":
        return key
    from .selfdata import self_dir
    return SELF_PREFIX + key + SELF_SEP + str(self_dir().resolve())


def is_sample(corpus=None) -> bool:
    """目前（或指定）的語料是不是 repo 內的公開範例語料。"""
    return not (corpus is None and os.environ.get("JOB_RAG_BUNDLE")) and _corpus_dir(corpus).resolve() == SAMPLE_CORPUS


def segments_hash(index_texts) -> str:
    return hashlib.sha1("\x00".join(index_texts).encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=2)
def _load_bundle(root: str) -> tuple:
    """(段落, 向量)。段落雜湊或筆數對不上就報錯，不用來路不明的向量。"""
    d = Path(root.removeprefix(BUNDLE_PREFIX))
    try:
        rows = [json.loads(l) for l in (d / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        z = np.load(d / "vectors.npz")
        vecs, want = z["vectors"], str(z["segments_sha1"])
    except (OSError, KeyError, ValueError) as e:
        raise RuntimeError(f"語料包讀不到或格式不對：{d}（{e}）") from e
    segs = tuple(r | {"excluded": False, "_index": f"{r['company']} {r['heading_path']}\n{r['text']}"} for r in rows)
    got = segments_hash(s["_index"] for s in segs)
    if got != want:
        raise RuntimeError(f"語料包段落雜湊對不上向量檔：段落 {got}，向量檔 {want}")
    if vecs.shape[0] != len(segs):
        raise RuntimeError(f"語料包向量筆數 {vecs.shape[0]} 與段落筆數 {len(segs)} 不同")
    return segs, vecs


def _company_of(path: list[str], stem: str, names: list[str]) -> str:
    """先看標題路徑（由外到內，第一個含公司名的標題）；沒有再看檔名。
    檔名含不只一家公司時不猜，歸「綜合」。"""
    pairs = [*ALIASES.items(), *((n, n) for n in names)]
    for t in path:
        for alias, name in pairs:
            if alias in t:
                return name
    in_stem = {name for alias, name in pairs if alias in stem}
    return in_stem.pop() if len(in_stem) == 1 else GENERAL


INTERVIEW = "面試"  # 含這兩字的內文行丟掉（面試資訊不是公開事實）；標題行不丟
# 第三方面試網站的內容（含表格列）本來就不是公司公開事實：整行丟掉，不留網址
THIRD_PARTY = re.compile("面試趣|面試心得|面試題|面試紀錄|面試區|GoodJob|goodjob")


def _strip_interview(line: str) -> str:
    """表格列（以 | 開頭）只清空含「面試」的欄位，其餘欄位保留；非表格行與第三方面試網站的列整行丟掉。
    回傳空字串＝整行不留。"""
    if INTERVIEW not in line:
        return line
    if not line.lstrip().startswith("|") or THIRD_PARTY.search(line):
        return ""
    cells = [("" if INTERVIEW in c else c) for c in line.split("|")]
    return "|".join(cells) if any(c.strip() for c in cells) else ""


DEEP_FILE = re.compile(r"^(0[1-9]|1[0-6]|S\d+)_")
DEEP_PREFIX = re.compile(r"^(?:\d+|S\d+)_")


@lru_cache(maxsize=4)
def _parse(root: str) -> tuple:
    """(段落, 被丟掉的面試行)。"""
    root_p = Path(root)
    files = sorted(root_p.rglob("*.md"))
    deep = lambda f: f.parent == root_p and DEEP_FILE.match(f.name)  # 一公司一檔；範例語料用 S1_ 這種編號
    names = [DEEP_PREFIX.sub("", f.stem) for f in files if deep(f)]
    segs, drops = [], []
    skip = frozenset() if root_p.resolve() == SAMPLE_CORPUS else EXCLUDED_COMPANIES
    for f in files:
        file_company = DEEP_PREFIX.sub("", f.stem) if deep(f) else None
        stack: list[tuple[int, str]] = []  # (level, title)，含 H1
        body: list[str] = []
        raw: list[str] = []  # 含「面試」行的原樣內文；只有排除（私人）段落用它，公開段落一律用 body
        dropped: list[str] = []

        def flush():
            path = [t for lv, t in stack if lv > 1]
            excluded = _is_excluded(path)
            text = "\n".join(raw if excluded else body).strip()
            body.clear(), raw.clear()
            company = file_company or _company_of(path, f.stem, names)
            if company in skip:  # 移出名單：連「面試」行的統計都不算
                dropped.clear()
                return
            for line in dropped:
                drops.append({"file": f.name, "heading_path": " > ".join(path) or f.stem,
                              "line": line, "public": not _is_excluded(path)})
            dropped.clear()
            if not text:
                return
            head = " > ".join(path) or (stack[0][1] if stack else f.stem)
            for piece in _pieces(text):
                segs.append({
                    "company": company, "file": f.name, "heading_path": head, "excluded": excluded,
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
                kept = _strip_interview(line)
                raw.append(line)
                if INTERVIEW in line:
                    dropped.append(line.strip())
                if kept:
                    body.append(kept)
        flush()
    return tuple(segs), tuple(drops)


def _segments(root: str) -> tuple:
    return _parse(root)[0]


def interview_drops(corpus=None) -> list[dict]:
    """被丟掉的「面試」行。public=True 的在公開事實段落內，才有誤丟公開內容的可能。"""
    return list(_parse(str(_corpus_dir(corpus).resolve()))[1])


def _tok(s: str) -> list[str]:
    return [t.lower() for t in jieba.cut_for_search(s) if re.search(r"\w", t)]


@lru_cache(maxsize=4)
def _public(root: str) -> tuple:
    """載入時就丟掉排除段落：往後的索引、快取、檢索都只看這裡。"""
    if root.startswith(SELF_PREFIX):
        return _self_pool(root)
    if root.startswith(BUNDLE_PREFIX):
        return _load_bundle(root)[0]
    return tuple(s for s in _segments(root) if not s["excluded"])


def _self_pool(key: str) -> tuple:
    """自用索引：公開事實段落＋語料中被排除的私人段落＋面經。只有自用鍵才會走到這裡。"""
    from .selfdata import load_interviews
    base, _, sd = key.removeprefix(SELF_PREFIX).partition(SELF_SEP)
    pub = tuple(s | {"private": False} for s in _public(base))
    if base.startswith(BUNDLE_PREFIX):
        notes = ()
    else:
        notes = tuple(s | {"private": True, "source": "筆記"} for s in _segments(base) if s["excluded"])
    names = {s["company"] for s in pub} - {GENERAL}
    return pub + notes + tuple(load_interviews(sd, names))


@lru_cache(maxsize=8)
def _bm25(root: str):
    pool = list(_public(root))
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
    """公開事實段落（依 _public 順序）的向量。磁碟快取；雜湊含公司與段落文字，
    分類規則或公司歸屬一改、段落清單變了就重算。"""
    if root.startswith(BUNDLE_PREFIX):
        if method != "bge-m3":
            raise RuntimeError(f"語料包只含 bge-m3 的向量，不支援 {method}")
        return _load_bundle(root)[1]
    segs = _public(root)
    h = segments_hash(s["_index"] for s in segs)
    tag = "self_" if root.startswith(SELF_PREFIX) else ""  # 展示的檔名維持原樣
    f = Path(os.environ.get("JOB_RAG_CACHE", ".cache")) / f"{method}_{tag}{h}.npy"
    if f.is_file():
        return np.load(f)
    v = _encode(method, [s["_index"] for s in segs], is_query=False)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.save(f, v)
    return v


@lru_cache(maxsize=8)
def _index(root: str, method: str):
    """(候選池, FAISS 內積索引)。"""
    import faiss
    pool = list(_public(root))
    if not pool:
        return pool, None
    vecs = _passage_vectors(root, method)
    idx = faiss.IndexFlatIP(vecs.shape[1])
    idx.add(np.ascontiguousarray(vecs))
    return pool, idx


def _rank_bm25(root, question, company):
    pool, bm = _bm25(root)
    if not pool:
        return pool, []
    scores = bm.get_scores(_tok(question))
    order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
    return pool, [(i, float(scores[i])) for i in order if scores[i] > 0 and (not company or pool[i]["company"] == company)]


def _rank_vector(root, method, question, company):
    pool, idx = _index(root, method)
    if not pool:
        return pool, []
    sims, ids = idx.search(_encode(method, [question], is_query=True), len(pool))
    return pool, [(int(i), float(s)) for s, i in zip(sims[0], ids[0]) if not company or pool[i]["company"] == company]


# 查無門檻：最高分低於它就回查無。用 bge-m3 的相似度（越高越像）；混合也用 bge-m3 的最高分判斷，
# 因為混合自己的 RRF 分數只看名次、不代表有多像。BM25 等其他方式沒做門檻。
# 值由 eval 的 30 題挑出（沒有獨立測試題），見 eval/results_methods.txt。
NOT_FOUND_THRESHOLD = 0.700
GATED = ("bge-m3", "hybrid")


def gate_score(question: str, method: str = "bge-m3", company: str | None = None, corpus=None, mode: str = "demo") -> float | None:
    """查無判斷用的最高分：bge-m3 與混合是 bge-m3 的最高相似度；其他方式沒做門檻回 None。"""
    if method not in GATED:
        return None
    _, ranked = _rank_vector(_root(corpus, mode), "bge-m3", question, company)
    return ranked[0][1] if ranked else None


def _detect(root: str, question: str) -> str | None:
    """問句整串含公司名或別名（公開段落的公司欄位＋ALIASES）才算；剛好一家才回傳。
    長的詞先比對並從問句剔除，所以短詞不會從長詞裡誤抓。"""
    names = {s["company"] for s in _public(root)} - {GENERAL}
    terms = {n: n for n in names} | {a: n for a, n in ALIASES.items() if n in names}
    found = set()
    for term in sorted(terms, key=len, reverse=True):
        if term in question:
            found.add(terms[term])
            question = question.replace(term, "\0")
    return found.pop() if len(found) == 1 else None


def mentions_company(question: str, corpus=None, mode: str = "demo") -> bool:
    """問句含任何一家公司的名稱或別名（不論幾家）。"""
    root = _root(corpus, mode)
    names = {s["company"] for s in _public(root)} - {GENERAL}
    return any(t in question for t in names | {a for a, n in ALIASES.items() if n in names})


def detect_company(question: str, corpus=None, mode: str = "demo") -> str | None:
    """問句只提到一家公司時回該公司，否則（沒有、兩家以上）回 None。"""
    return _detect(_root(corpus, mode), question)


def _same_text(s: str) -> str:
    """去重用的正規化：全形轉半形、去掉所有空白。標點與大小寫不動（可能有意義）。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def _dedupe(pool, ranked):
    """同公司、正規化後文字相同的段落只留名次最前（分數最高）的，其餘位置記進 also_in。"""
    kept, seen = [], {}
    for i, sc in ranked:
        key = (pool[i]["company"], _same_text(pool[i]["text"]))
        if key in seen:
            seen[key].append({"file": pool[i]["file"], "heading_path": pool[i]["heading_path"]})
        else:
            seen[key] = []
            kept.append((i, sc, seen[key]))
    return kept


DEFAULT_METHOD, DEFAULT_K = "bge-m3", 3  # 預設檢索方式與取前幾段（介面與 /about 都讀這兩個）


def search(question: str, method: str = DEFAULT_METHOD, company: str | None = None,
           k: int = DEFAULT_K, corpus=None, gate: bool = True, detect: bool = False, dedupe: bool = False,
           mode: str = "demo") -> list[dict]:
    """排序後的公開事實段落。排除段落在載入時就丟了，候選池根本沒有它們。
    查無（最高分低於 NOT_FOUND_THRESHOLD）回空串列；gate=False 不套門檻（評分用）。
    detect：沒指定 company 時，問句只含一家公司名就只搜那家。dedupe：合併重複段落，結果多一個 also_in。"""
    if method not in METHODS:
        raise ValueError(f"未支援的檢索方式：{method}")
    root = _root(corpus, mode)
    if detect and not company:
        company = _detect(root, question)
    top = None  # 查無判斷用的分數（只有 GATED 方式有）
    if method == "bm25":
        pool, ranked = _rank_bm25(root, question, company)
    elif method == "hybrid":
        pool, rb = _rank_bm25(root, question, company)
        _, rv = _rank_vector(root, "bge-m3", question, company)
        ranked, top = rrf([[i for i, _ in rb], [i for i, _ in rv]]), (rv[0][1] if rv else None)
    else:
        pool, ranked = _rank_vector(root, method, question, company)
        top = ranked[0][1] if ranked and method in GATED else None
    if gate and method in GATED and (top is None or top < NOT_FOUND_THRESHOLD):
        return []
    rows = _dedupe(pool, ranked) if dedupe else [(i, sc, None) for i, sc in ranked]
    return [{key: pool[i][key] for key in ("company", "file", "heading_path", "text")} | {"score": float(sc)}
            | ({} if also is None else {"also_in": also}) | ({"private": pool[i]["private"]} if mode == "self" else {})
            for i, sc, also in rows[:k]]


def classification_table(corpus=None) -> list[dict]:
    """標題 × 公開／排除 × 段落數，給人檢查分類。"""
    counts: dict[tuple[str, bool], int] = {}
    for s in _segments(str(_corpus_dir(corpus).resolve())):
        key = (s["_title"], s["excluded"])
        counts[key] = counts.get(key, 0) + 1
    return [{"title": t, "excluded": e, "count": n} for (t, e), n in sorted(counts.items(), key=lambda kv: (kv[0][1], kv[0][0]))]


def public_company_counts(corpus=None, mode: str = "demo") -> dict[str, int]:
    """公司 -> 段落數（「綜合」＝無法歸屬）。展示模式只算公開事實段落；自用模式也算私人段落與面經。"""
    out: dict[str, int] = {}
    for s in _public(_root(corpus, mode)):
        out[s["company"]] = out.get(s["company"], 0) + 1
    return dict(sorted(out.items()))

"""白名單匯出：python -X utf8 scripts/export_public_repo.py [輸出資料夾，預設 dist/public_repo]
預設拒絕：只複製下面 FILES／GLOBS 明列的檔案，其他一律不碰。匯出後再掃一遍（私人字串、金鑰、電話、信箱、禁止的路徑），
有任何發現就刪掉輸出並以非 0 結束。輸出資料夾沒有 git 歷史；要公開時由使用者自己在那裡 git init。
真語料的檔名清單來自環境變數 JOB_RAG_REAL_CORPUS（有設才逐字比對）。這個腳本與它的測試不會被複製到公開版。"""
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 公開版路徑 -> 私人 repo 路徑（必要檔；缺一個就報錯）
FILES = {
    "app.py": "app.py", "start_phone.bat": "start_phone.bat", ".env.example": "public/env.example",  # 公開版的 .env.example 不含自用設定
    "requirements.txt": "requirements.txt", "requirements-ragas.txt": "requirements-ragas.txt",
    "requirements-vector.txt": "requirements-vector.txt",
    "README.md": "public/README.md", "start.bat": "public/start.bat", ".gitignore": "public/gitignore",  # 公開版專用範本
    "eval/questions.sample.json": "eval/questions.sample.json",
}
# 只複製這些樣式的檔案（副檔名也限制；scripts/ 只有圖示腳本；匯出腳本、通道啟動檔 start_public.*、個人用途的腳本都不含）
GLOBS = ["job_rag/*.py", "job_rag/company_presets.json", "scripts/make_icons.py", "static/*.png", "tests/*.py", "tests/fixtures/mini/**/*.md", "sample_corpus/**/*.md"]
NOT_PUBLIC = {"tests/test_export_public.py"}  # 匯出腳本的測試依賴私人 repo 的檔案

FORBIDDEN_PARTS = {".git", ".scratch", "demo", "models", ".cache", "dist", "docs", ".env", "SPEC.md", "GLOSSARY.md", "CLAUDE.md", "selfdata"}  # selfdata：自用資料（票 24）
ALLOWED_EVAL = {"eval/questions.sample.json"}
# 這些字眼只准出現在「分類與過濾私人段落」的程式與它的測試、假語料裡（它們必須叫得出被排除的類別）
WORDS = re.compile("履歷|面試|評價|風險|判斷|作戰|媒合|廠商深查|求職策略|協作")
WORD_OK = ("job_rag/retrieval.py", "job_rag/evaluate.py", "job_rag/classify.py", "job_rag/selfdata.py", "tests/")
PATTERNS = {
    "hf 金鑰": re.compile(r"\bhf_\w+"), "sk 金鑰": re.compile(r"\bsk-\w+"),
    "電子郵件": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "手機": re.compile(r"(?<![\w.-])09\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)"),
    "市話": re.compile(r"(?<![\w.-])\(?0\d{1,2}\)?[- ]?\d{3,4}[- ]?\d{4}(?!\d)"),
    "私人路徑或帳號": re.compile(r"C:\\claude|cygnu|hh123456|henry6655", re.I),
    "通道或密碼檔名稱": re.compile(r"ngrok|tracing-herbs|owner_pin\.txt", re.I),  # 任何檔案都不准提
    "密碼檔名（小寫）": re.compile(r"owner_pin"),  # 環境變數 JOB_RAG_OWNER_PIN 是大寫，不受影響
    "存取碼被賦值": re.compile(r"ACCESS_CODE\s*[=:]\s*[^\s\"'#]"),  # 同上：只准寫變數名稱
    "本人密碼被賦值": re.compile(r"OWNER_PIN\s*[=:]\s*[^\s\"'#]"),  # 只准寫變數名稱，不准寫值（空值的範例可以）
}
SELF_PATH = re.compile(r"selfdata[/\\]")
SURVEY_NAME = re.compile(r"(?<![\w])(?:0[0-9]|1[0-6])_[^\s\"'`,)\]/\\<>|]+?\.md")
# 假語料用的檔名（測試與 fixtures）：樣式像完整語料，但不是真檔名
FAKE_NAMES = {"01_甲科技.md", "01_甲.md", "02_乙.md", "02_乙資訊.md", "01_丙公司.md", "03_丙.md", "04_丁.md", "03_神通資訊.md",
              "04_聯合報.md", "02_藍新資訊.md", "07_台灣大哥大.md", "00_排除範例.md"}


def collect(root) -> tuple[list[tuple[str, str]], list[str]]:
    """(要複製的 (來源, 目的) 清單, 缺少的白名單檔)。來源與目的都是相對路徑。"""
    root, copies, missing = Path(root), [], []
    for dst, src in FILES.items():
        if (root / src).is_file():
            copies.append((src, dst))
        else:
            missing.append(dst)
    for pat in GLOBS:
        hits = sorted(p.relative_to(root).as_posix() for p in root.glob(pat) if p.is_file())
        hits = [h for h in hits if h not in NOT_PUBLIC and "__pycache__" not in h]
        copies += [(h, h) for h in hits]
        if not hits:
            missing.append(pat)
    return copies, missing


def _read(p: Path):
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:  # 圖示等二進位檔
        return None


def scan(out, real_names=(), secrets=()) -> list[str]:
    """回傳發現清單，空串列＝乾淨。secrets：絕不能出現在任何檔案內容裡的字串（本人密碼的值、面經內文片段）；只回報檔名，不回報內容。"""
    out, found = Path(out), []
    for p in sorted(out.rglob("*")):
        rel = p.relative_to(out).as_posix()
        parts = rel.split("/")
        bad_env = p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example")
        if bad_env or p.name.startswith(".venv") or any(x in FORBIDDEN_PARTS for x in parts):
            found.append(f"{rel}：禁止的路徑")
        if parts[0] == "eval" and p.is_file() and rel not in ALLOWED_EVAL:
            found.append(f"{rel}：eval/ 只准放範例評估題")
        name = parts[-1]
        if p.is_file() and SURVEY_NAME.fullmatch(name) and name not in FAKE_NAMES:
            found.append(f"{rel}：完整語料的檔名樣式")
        if not p.is_file():
            continue
        if (txt := _read(p)) is None:
            continue
        for label, rx in PATTERNS.items():
            found += [f"{rel}：{label}：{m.group(0)}" for m in rx.finditer(txt)]
        if rel != "job_rag/selfdata.py":  # 自用資料夾的路徑：只有讀它的那個模組可以提
            found += [f"{rel}：自用資料夾路徑：{m.group(0)}" for m in SELF_PATH.finditer(txt)]
        if not rel.startswith(WORD_OK):
            found += [f"{rel}：私人用語：{m.group(0)}" for m in WORDS.finditer(txt)]
        found += [f"{rel}：完整語料的檔名：{m.group(0)}" for m in SURVEY_NAME.finditer(txt) if m.group(0) not in FAKE_NAMES]
        found += [f"{rel}：真語料檔名：{n}" for n in real_names if n.endswith(".md") and (n in txt or n in rel)]
        found += [f"{rel}：含自用資料或本人密碼的值" for v in secrets if v and v in txt]
    return found


def export(root, out) -> list[tuple[str, str]]:
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.name != "public_repo" or out == root or root.is_relative_to(out):
        raise ValueError(f"輸出資料夾必須叫 public_repo，且不能是專案根目錄或它的上層：{out}")
    copies, missing = collect(root)
    if missing:
        raise FileNotFoundError("白名單檔案不存在：" + "、".join(missing))
    if out.exists():
        shutil.rmtree(out)
    for src, dst in copies:
        (out / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / src, out / dst)
    return copies


def self_secrets() -> list[str]:
    """本機才有的東西：本人密碼的值，以及面經每段內文開頭 24 字（逐字比對公開輸出）。沒設或沒有就是空的。"""
    import json
    out = [v for v in (os.environ.get("JOB_RAG_OWNER_PIN", ""),) if v]
    sys.path.insert(0, str(ROOT))
    from job_rag.selfdata import self_dir
    root = Path(self_dir(), "面經")
    for f in root.rglob("*.jsonl") if root.is_dir() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            secs = r.get("sections") if isinstance(r.get("sections"), list) else []
            for t in [x.get("content") for x in secs if isinstance(x, dict)] + [r.get("process_text")]:
                if isinstance(t, str) and len(t.strip()) >= 24:
                    out.append(t.strip()[:24])
    return out


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "public_repo"
    corpus = os.environ.get("JOB_RAG_REAL_CORPUS")
    names = [f.name for f in Path(corpus).rglob("*.md")] if corpus and Path(corpus).is_dir() else []
    copies = export(ROOT, out)
    found = scan(out, real_names=names, secrets=self_secrets())
    if found:
        shutil.rmtree(out)
        print(f"掃描發現 {len(found)} 項，已刪除輸出：", *found, sep="\n  ")
        sys.exit(1)
    total = 0
    for _, dst in sorted(copies, key=lambda c: c[1]):
        size = (out / dst).stat().st_size
        total += size
        print(f"{size:>9,}  {dst}")
    print(f"\n匯出 {len(copies)} 個檔案、{total / 1e3:.1f} KB 到 {out}；掃描乾淨"
          + ("" if names else "（沒設 JOB_RAG_REAL_CORPUS：略過真語料檔名逐字比對）"))


if __name__ == "__main__":
    main()

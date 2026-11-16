"""票 09：白名單匯出。只在私人 repo 跑；匯出時不會複製這個檔（公開版沒有 scripts/export_public_repo.py）。"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import export_public_repo as ex  # noqa: E402


def _touch(root, rel, text="x\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---- 預設拒絕：沒列在白名單的檔案一律不複製 ----
def test_collect_copies_only_listed_files_and_denies_everything_else(tmp_path):
    for rel in ("app.py", "job_rag/a.py", "tests/test_a.py", "tests/test_export_public.py", "SPEC.md", "GLOSSARY.md", "CLAUDE.md",
                ".env", ".env.local", ".scratch/x.md", "docs/agents/a.md", "demo/a.html", "models/m.bin", ".cache/a.npy",
                "dist/public_repo/app.py", ".venv/a.py", ".venv-ragas/a.py", "job_rag/notes.txt", "job_rag/__pycache__/a.pyc",
                "scripts/other_personal.py", "eval/questions.json", "eval/results_methods.json", "eval/button_check.md",
                "eval/crossjudge/judge_gpt.json", "eval/estimate_generation.txt", "smoke_deepseek.py", "static/notes.txt", "README.md"):
        _touch(tmp_path, rel)
    copies, _ = ex.collect(tmp_path)
    got = {dst for _, dst in copies}
    assert got == {"app.py", "job_rag/a.py", "tests/test_a.py"}, got  # 私人的 README.md 不複製；公開版 README 來自 public/


def test_collect_reports_missing_whitelisted_files(tmp_path):
    _touch(tmp_path, "app.py")
    _, missing = ex.collect(tmp_path)
    assert "start_phone.bat" in missing and "app.py" not in missing


def test_public_files_come_from_the_public_templates():
    copies, missing = ex.collect(ROOT)
    assert missing == []
    src = dict((d, s) for s, d in copies)
    assert src["README.md"] == "public/README.md" and src["start.bat"] == "public/start.bat" and src[".gitignore"] == "public/gitignore"
    assert "scripts/export_public_repo.py" not in src and "tests/test_export_public.py" not in src
    assert {"sample_corpus/S1_奧衍.md", "eval/questions.sample.json", "static/icon-192.png", "scripts/make_icons.py"} <= set(src)


# ---- 票 26：公開版要能跑現在的程式，但不帶通道啟動檔與自用設定 ----
def test_export_includes_everything_the_app_imports_and_reads():
    src = {d for _, d in ex.collect(ROOT)[0]}
    assert {"job_rag/company_presets.json", "job_rag/guard.py", "job_rag/memory.py", "job_rag/owner.py", "job_rag/chat_ui.py",
            "job_rag/about_page.py", "start.bat", "start_phone.bat", ".env.example"} <= src
    for tunnel in ("start_public.bat", "scripts/start_public.ps1", "scripts/check_self_presets.py", "scripts/gen_company_presets.py",
                   "scripts/export_public_repo.py", "smoke_deepseek.py"):
        assert tunnel not in src, tunnel


def test_collect_never_copies_tunnel_launchers_even_if_present(tmp_path):
    for rel in ("app.py", "start_public.bat", "scripts/start_public.ps1", "scripts/check_self_presets.py", "job_rag/company_presets.json"):
        _touch(tmp_path, rel)
    got = {dst for _, dst in ex.collect(tmp_path)[0]}
    assert got == {"app.py", "job_rag/company_presets.json"}


def test_public_env_example_has_no_self_mode_setting(exported):
    env = (exported / ".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in env and "OWNER_PIN" not in env and "SELF_DIR" not in env


def test_public_readme_title_matches_ui_and_has_no_private_topics(exported):
    txt = (exported / "README.md").read_text(encoding="utf-8")
    assert txt.splitlines()[0] == "# 求職情報問答"
    for w in ("自用", "OWNER", "PIN", "協作", "ngrok", "存取碼", "ACCESS_CODE", "履歷", "求職策略", "selfdata"):
        assert w not in txt, w
    for w in ("公司對話頁", "預設題目", "追問", "查無", "專案說明", "信賴區間", "English summary"):
        assert w in txt, w


# ---- 掃描：每條規則都要有抓得到、和抓不到的例子 ----
def _scan(tmp_path, rel, text, **kw):
    _touch(tmp_path, rel, text)
    return ex.scan(tmp_path, **kw)


@pytest.mark.parametrize("text", [
    "token = hf_AbCdEf123456", "key = sk-abc123def", "寄到 someone@example.com", "電話 0912-345-678", "電話 (02) 2345-6789 或 02-2345-6789",
    r"路徑 C:\claude\x", "使用者 cygnu", "帳號 hh123456", "帳號 henry6655", "我的履歷", "面試心得", "公司評價", "有風險", "我的判斷", "面談作戰卡",
    "ngrok http 5000", "https://x.tracing-herbs.ngrok.app", "JOB_RAG_ACCESS_CODE=abc-123", "set JOB_RAG_ACCESS_CODE=abc", "owner_pin.txt",
    "ACCESS_CODE: abc123", "AI 協作紀錄", "AI協作",
])
def test_scan_catches_private_strings(tmp_path, text):
    assert _scan(tmp_path, "app.py", text + "\n"), text


@pytest.mark.parametrize("text", [
    "task-list and shelf_life", "sk 是縮寫", "2026-06-30 資本額 20,000,000 元", "統編 28132571", "https://www.104.com.tw/job/91s39",
    "DEEPSEEK_API_KEY=", "# 這是 .env.example 的說明", "NT$1,260／月", "email 欄位", "model@2x 圖示", "公司的月薪 35,000~46,000 元",
])
def test_scan_does_not_flag_look_alikes(tmp_path, text):
    assert _scan(tmp_path, "app.py", text + "\n") == [], text


def test_scan_flags_forbidden_paths_and_real_survey_file_names(tmp_path):
    for rel in (".env", "models/a.bin", ".cache/a.npy", "dist/a", ".venv/a", ".git/config", "SPEC.md", ".scratch/a.md", "eval/results_x.txt"):
        assert _scan(tmp_path / rel.replace("/", "_"), rel, "x\n"), rel
    assert _scan(tmp_path / "ok", ".env.example", "DEEPSEEK_API_KEY=\n") == []
    assert _scan(tmp_path / "n1", "sample_corpus/08_奧衍.md", "# x\n")  # 完整語料的檔名樣式
    assert _scan(tmp_path / "n2", "tests/a.py", "open('08_奧衍.md')\n")
    assert _scan(tmp_path / "n3", "tests/a.py", "open('01_甲科技.md')\n") == []  # 假語料的檔名可以
    assert _scan(tmp_path / "n4", "tests/a.py", "x = '補9_神通.md'\n", real_names=["補9_神通.md"])  # 真語料資料夾裡的檔名，逐字比對


def test_scan_allows_filter_words_only_in_the_filter_code_and_its_tests(tmp_path):
    assert _scan(tmp_path / "a", "job_rag/retrieval.py", "# 面試 風險 評價\n") == []
    assert _scan(tmp_path / "b", "tests/test_x.py", "面試 風險\n") == []
    assert _scan(tmp_path / "c", "tests/fixtures/mini/a.md", "## 面試\n") == []
    assert _scan(tmp_path / "d", "README.md", "面試\n")
    assert _scan(tmp_path / "e", "app.py", "判斷\n")
    assert _scan(tmp_path / "f", "job_rag/retrieval.py", "cygnu\n")  # 帳號、路徑、金鑰類沒有例外


def test_scan_blocks_self_data_folder_and_pin_values_but_allows_variable_names(tmp_path):  # 票 24
    assert _scan(tmp_path / "a", "selfdata/面經/goodjob/甲.jsonl", "x\n")  # 路徑本身就禁止
    assert _scan(tmp_path / "b", "tests/fixtures/selfdata/a.md", "x\n")
    assert _scan(tmp_path / "c", "app.py", "x = 'fake-pin-value-9'\n", secrets=["fake-pin-value-9"])  # 密碼的值出現在任何檔案
    assert _scan(tmp_path / "d", ".env.example", "JOB_RAG_OWNER_PIN=abc123\n")  # 賦值
    assert _scan(tmp_path / "e", "README.md", "OWNER_PIN: abc123\n")
    assert _scan(tmp_path / "f", ".env.example", "JOB_RAG_OWNER_PIN=\n# JOB_RAG_SELF_DIR=\n") == []  # 空值與只寫名稱可以
    assert _scan(tmp_path / "g", "app.py", "os.environ.get('JOB_RAG_OWNER_PIN', '')\n") == []
    assert _scan(tmp_path / "h", "tests/test_a.py", "monkeypatch.setenv('JOB_RAG_OWNER_PIN', PIN)\n") == []
    assert _scan(tmp_path / "i", "app.py", "面經內文開頭二十四個字的片段在這裡出現了\n", secrets=["面經內文開頭二十四個字的片段在這裡出現了"])
    assert _scan(tmp_path / "j", "app.py", "完全不相干\n", secrets=["", "面經內文"]) == []  # 空字串不算，沒出現不算


def test_scan_blocks_self_data_path_mentions_except_in_the_self_data_module(tmp_path):
    assert _scan(tmp_path / "a", "README.md", "資料放在 selfdata/面經\n") and _scan(tmp_path / "b", "app.py", "open('selfdata/x')\n")
    assert _scan(tmp_path / "c", "job_rag/selfdata.py", "# selfdata/面經/**/*.jsonl\n") == []
    assert _scan(tmp_path / "d", "job_rag/selfdata.py", "owner_pin.txt\n")  # 密碼檔名任何地方都不准


def test_self_mode_words_are_allowed_only_in_the_self_data_module(tmp_path):
    assert _scan(tmp_path / "a", "job_rag/selfdata.py", "面試 作戰 風險 評價\n") == []
    assert _scan(tmp_path / "b", "job_rag/owner_ui.py", "面試\n") and _scan(tmp_path / "c", "app.py", "風險\n")


def test_export_whitelist_never_copies_self_data_even_if_present(tmp_path):
    for rel in ("app.py", "selfdata/面經/goodjob/甲.jsonl", "job_rag/selfdata/x.jsonl", "tests/selfdata/a.jsonl", ".env.local"):
        _touch(tmp_path, rel)
    got = {dst for _, dst in ex.collect(tmp_path)[0]}
    assert got == {"app.py"}


# ---- 真的匯出 ----
@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("pub") / "public_repo"
    ex.export(ROOT, out)
    return out


def test_real_export_passes_scan_and_has_no_git_history(exported):
    real = os.environ.get("JOB_RAG_REAL_CORPUS")
    names = [f.name for f in Path(real).rglob("*.md")] if real and Path(real).is_dir() else []
    assert ex.scan(exported, real_names=names, secrets=ex.self_secrets()) == []  # 票 24：本機的密碼值與面經片段也不能在裡面
    assert not (exported / "selfdata").exists() and not list(exported.rglob("*.jsonl"))
    assert not list(exported.rglob(".git*")) or [p.name for p in exported.rglob(".git*")] == [".gitignore"]


def test_export_replaces_old_output_and_refuses_unsafe_target(tmp_path):
    out = tmp_path / "dist" / "public_repo"
    out.mkdir(parents=True)
    (out / "stale.txt").write_text("old", encoding="utf-8")
    ex.export(ROOT, out)
    assert not (out / "stale.txt").exists() and (out / "app.py").is_file()
    with pytest.raises(ValueError):  # 不能把輸出指到專案根目錄或它的上層：會清掉原始碼
        ex.export(ROOT, ROOT)
    with pytest.raises(ValueError):
        ex.export(ROOT, ROOT.parent)


def test_exported_start_bat_has_no_absolute_path_and_keeps_phone_opt_in(exported):
    bat = (exported / "start.bat").read_text(encoding="utf-8")
    assert "%~dp0sample_corpus" in bat and ":\\" not in bat.replace("%~dp0", "")
    assert bat.count("JOB_RAG_HOST=0.0.0.0") == 1 and "phone" in bat.split("JOB_RAG_HOST=0.0.0.0")[0].splitlines()[-1].lower()

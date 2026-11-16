"""範例語料（sample_corpus/）與範例評估題（eval/questions.sample.json）：載入流程讀得到、沒有排除段落、題目引文對得上。"""
import json
from pathlib import Path

import pytest

from job_rag import classification_table, public_company_counts, retrieval, search
from job_rag.evalset import verify

ROOT = Path(__file__).parent.parent
SAMPLE = ROOT / "sample_corpus"
QUESTIONS = ROOT / "eval" / "questions.sample.json"


def test_sample_prefixed_file_is_a_per_company_file(tmp_path):
    # 範例語料的檔名用 S1_公司.md：和真語料的編號檔同樣，公司由檔名決定
    for n, (name, word) in enumerate([("丙科技", "海星"), ("丁科技", "珊瑚"), ("戊科技", "貝殼")], 1):
        (tmp_path / f"S{n}_{name}.md").write_text(f"# {name}\n## 1. 基本資料\n獨特詞彙：{word}。\n", encoding="utf-8")
    r = search("海星", method="bm25", corpus=tmp_path)  # BM25 的詞要出現在少於一半的段落才有分數，所以放三家
    assert r and r[0]["company"] == "丙科技"


def test_sample_corpus_has_three_companies_and_no_excluded_segment():
    rows = classification_table(SAMPLE)
    assert rows and not [r for r in rows if r["excluded"]]  # 排除段落數 0
    counts = public_company_counts(SAMPLE)
    assert set(counts) == {"奧衍", "尼諾思科技", "遠振資訊"}  # 沒有「綜合」
    assert sum(counts.values()) == sum(r["count"] for r in rows)


def test_sample_corpus_files_do_not_use_real_survey_file_names():
    import re
    assert not [f.name for f in SAMPLE.rglob("*.md") if re.match(r"^(0[1-9]|1[0-6])_", f.name)]


def test_sample_questions_verify_against_sample_corpus():
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    assert verify(qs, SAMPLE) == []
    assert sum(q["answerable"] for q in qs) >= 6 and sum(not q["answerable"] for q in qs) >= 2
    assert all(q.get("source") for q in qs)  # 每題標明來源


# ---- 題目檔位置：有完整題組用完整的，只有範例題組就用範例的 ----
def test_questions_path_prefers_full_set_and_falls_back_to_sample(tmp_path):
    from job_rag.evalset import questions_path
    (tmp_path / "eval").mkdir()
    with pytest.raises(FileNotFoundError):  # 兩個都沒有：明確報錯，不回預設內容
        questions_path(tmp_path)
    (tmp_path / "eval" / "questions.sample.json").write_text("{}", encoding="utf-8")
    assert questions_path(tmp_path).name == "questions.sample.json"
    (tmp_path / "eval" / "questions.json").write_text("{}", encoding="utf-8")
    assert questions_path(tmp_path).name == "questions.json"

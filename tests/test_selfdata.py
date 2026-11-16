"""票 24：面經載入器。全部用手寫假資料，不讀真的自用資料夾。"""
import json

from job_rag.selfdata import article_counts, load_interviews

NAMES = {"甲科技", "乙資訊"}


def write(d, sub, name, rows, raw_lines=()):
    p = d / "面經" / sub
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{name}.jsonl").write_text("\n".join([json.dumps(r, ensure_ascii=False) for r in rows] + list(raw_lines)), encoding="utf-8")


def gj(**kw):
    r = {"source": "goodjob.life", "company": "甲科技股份有限公司", "share_date": "2024-11-05T04:10:34Z", "interview_time": "2024-05",
         "job_title": "後端工程師", "result": "錄取", "locked": False, "window_ok": True,
         "sections": [{"subtitle": "面試過程", "content": "假內文：先筆試再面談。"}, {"subtitle": "建議", "content": "假建議。"}],
         "interview_qas": [{"question": "假問題一", "answer": "假回答一"}]}
    return r | kw


def test_goodjob_article_is_split_by_section_with_title_structure(tmp_path):
    write(tmp_path, "goodjob", "甲科技", [gj()])
    segs = load_interviews(tmp_path, NAMES)
    assert {s["company"] for s in segs} == {"甲科技"} and all(s["private"] and s["source"] == "面經" for s in segs)
    heads = [s["heading_path"] for s in segs]
    assert "面經（GoodJob）｜2024-05｜後端工程師 > 面試過程" in heads and "面經（GoodJob）｜2024-05｜後端工程師 > 建議" in heads
    assert any("假問題一" in s["text"] and "假回答一" in s["text"] for s in segs)
    assert any("錄取" in s["text"] for s in segs)


def test_only_window_ok_true_unlocked_nonempty_are_loaded(tmp_path):
    rows = [gj(), gj(window_ok=False, job_title="A"), gj(window_ok=None, job_title="B"), gj(locked=True, job_title="C"),
            gj(sections=[], interview_qas=[], job_title="D"), gj(sections=[{"subtitle": "x", "content": "  "}], interview_qas=[], job_title="E")]
    r_missing = gj(job_title="F")
    del r_missing["window_ok"]
    write(tmp_path, "goodjob", "甲科技", rows + [r_missing], raw_lines=["not json", "[1]", ""])
    segs = load_interviews(tmp_path, NAMES)
    assert {s["heading_path"].split(" > ")[0].split("｜")[-1] for s in segs} == {"後端工程師"}
    assert article_counts(tmp_path, NAMES) == {"甲科技": 1}


def test_company_comes_from_file_name_else_field_else_skipped(tmp_path):
    write(tmp_path, "goodjob", "乙資訊", [gj(company="別名公司")])             # 檔名對得到
    write(tmp_path, "goodjob", "某某金控", [gj(company="甲科技股份有限公司")])  # 檔名不是公司，欄位含公司名
    write(tmp_path, "goodjob", "丙公司", [gj(company="丙公司")])               # 都對不到：略過
    assert article_counts(tmp_path, NAMES) == {"乙資訊": 1, "甲科技": 1}


def test_interview_tw_shape_and_locked_file_skipped(tmp_path):
    tw = {"source": "interview.tw", "company": "乙資訊", "position": "資料工程師", "interview_month": "2025-03", "result": "錄取",
          "process_text": "假流程文字", "qa": [{"q": "假題", "a": "假答"}], "locked": False, "window_ok": True}
    write(tmp_path, "interview_tw", "乙資訊", [tw])
    write(tmp_path, "interview_tw", "甲科技", [tw | {"locked": True}])  # 被鎖：略過
    segs = load_interviews(tmp_path, NAMES)
    assert {s["company"] for s in segs} == {"乙資訊"}
    assert segs[0]["heading_path"].startswith("面經（面試趣）｜2025-03｜資料工程師")
    assert any("假流程文字" in s["text"] for s in segs) and any("假題" in s["text"] for s in segs)


def test_long_section_is_cut_into_chunks(tmp_path):
    write(tmp_path, "goodjob", "甲科技", [gj(sections=[{"subtitle": "長", "content": "字" * 1500}], interview_qas=[])])
    segs = load_interviews(tmp_path, NAMES)
    assert len(segs) >= 3 and all(len(s["text"]) <= 700 for s in segs)


def test_missing_dir_or_empty_dir_is_empty_not_error(tmp_path):
    assert load_interviews(tmp_path / "nope", NAMES) == [] and load_interviews(tmp_path, NAMES) == []
    assert article_counts(tmp_path / "nope", NAMES) == {}

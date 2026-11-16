"""票 22 前端：最近 2 輪只從該對話框取、不外洩到別的對話框。腳本用靜態檢查；真的跨框行為由瀏覽器驗證（見回報）。"""
import re
import shutil
import subprocess
from urllib.parse import quote

import pytest

from job_rag.chat_ui import CHAT_JS
from tests.test_chat import web  # noqa: F401
from tests.test_vector import fake_env  # noqa: F401  (autouse fixture)


def test_script_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("沒有 node")
    r = subprocess.run([node, "--check", "-"], input=CHAT_JS, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr


def test_history_lives_in_the_per_dialog_storage_key_and_nowhere_else():
    assert "KEY='jr_chat:'+MODE+':'+B.dataset.key" in CHAT_JS
    assert "JSON.stringify({html:T.innerHTML,hist:hist})" in CHAT_JS  # 與該對話框的畫面一起存
    assert "localStorage" not in CHAT_JS and "window." not in CHAT_JS and "document.cookie" not in CHAT_JS
    assert CHAT_JS.count("var hist") + CHAT_JS.count(",hist=[]") == 1  # 一個閉包變數，沒有跨頁共用的全域


def test_only_the_last_two_turns_are_sent_and_cut_to_the_server_limits():
    assert "hist.slice(-2)" in CHAT_JS and "q.slice(0,200)" in CHAT_JS and "a.slice(0,300)" in CHAT_JS
    assert CHAT_JS.count("hp({q:q") == 2  # /api/search 與 /api/answer 都帶
    assert "p.history=HJ" in CHAT_JS and "var HJ=hist.length?hjson():''" in CHAT_JS  # 送出當下的快照，不含本題


def test_a_turn_is_recorded_only_after_its_answer_and_failures_are_not_recorded():
    assert CHAT_JS.count("rec(q,") - 1 == 4  # 答案、查無、搜尋低分、答案低分
    for l in CHAT_JS.splitlines():
        if "el('p','err'" in l or "bad(" in l:  # 錯誤路徑的行
            assert "rec(" not in l, l


def test_stored_history_is_type_checked_before_use():
    assert "Array.isArray(old.hist)" in CHAT_JS and "typeof t.q==='string'" in CHAT_JS


def test_follow_up_completion_is_shown_as_a_real_step():
    assert "if(j.expanded)step('問題很短，接上一題一起搜尋')" in CHAT_JS


def test_each_company_page_has_its_own_storage_key(web):  # noqa: F811
    c = web.app.test_client()
    ka = re.search(r'data-key="([^"]*)"', c.get("/c/" + quote("台灣大哥大")).get_data(as_text=True)).group(1)
    kb = re.search(r'data-key="([^"]*)"', c.get("/c/" + quote("藍新資訊")).get_data(as_text=True)).group(1)
    assert ka == "台灣大哥大" and kb == "藍新資訊" and ka != kb

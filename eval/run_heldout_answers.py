"""票 39：獨立測試題 40 題對主服務實跑一次，記下實際答案：python -X utf8 eval/run_heldout_answers.py [--base URL] [--max-calls 60]
流程與 eval/run_answers.py 相同（只換題組與輸出檔）：寫入 eval/results_heldout_answers.json。DeepSeek 呼叫上限預設 60，間隔 ≥ 1 秒；遇到每小時上限就停止。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_answers  # noqa: E402

run_answers.OUT = Path(__file__).parent / "results_heldout_answers.json"
run_answers.SETS = ("questions_heldout",)
if "--max-calls" not in sys.argv:
    sys.argv += ["--max-calls", "60"]
sys.exit(run_answers.main())

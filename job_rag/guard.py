"""公開網址前的保護：存取碼比對與「整理成答案」的全域用量上限。"""
import hmac
import math
import os
import time
from collections import deque

COOKIE = "jr_k"
DEFAULT_LIMIT = 100
WINDOW = 3600  # 秒；滑動視窗


def access_code() -> str:
    return os.environ.get("JOB_RAG_ACCESS_CODE", "")


def code_ok(given: str, code: str) -> bool:
    """常數時間比對。先轉 bytes：非 ASCII 字串直接丟給 compare_digest 會 TypeError。"""
    return bool(code) and hmac.compare_digest(given.encode("utf-8"), code.encode("utf-8"))


def answer_limit() -> int:
    try:
        n = int(os.environ.get("JOB_RAG_ANSWER_LIMIT", ""))
    except ValueError:
        return DEFAULT_LIMIT
    return n if n > 0 else DEFAULT_LIMIT


class RateLimit:
    """全域滑動視窗計數。clock 可注入（測試用）。"""

    def __init__(self, clock=time.monotonic, window=WINDOW):
        self.clock, self.window, self.stamps = clock, window, deque()

    def try_acquire(self, limit: int) -> int:
        """允許時記一次並回 0；超過上限時回要再等幾秒（至少 1）。"""
        now = self.clock()
        while self.stamps and self.stamps[0] <= now - self.window:
            self.stamps.popleft()
        if len(self.stamps) >= limit:
            return max(1, math.ceil(self.stamps[0] + self.window - now))
        self.stamps.append(now)
        return 0

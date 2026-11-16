"""本人密碼（票 24）：常數時間比對、全域錯誤次數上限、簽名 cookie。
簽章金鑰在建立物件時隨機產生，重啟即失效。沒設 JOB_RAG_OWNER_PIN 就沒有自用模式。"""
import hashlib
import hmac
import os
import secrets
import time
from collections import deque

COOKIE = "jr_owner"
TTL = 8 * 3600
FAIL_LIMIT, FAIL_WINDOW = 5, 600  # 10 分鐘 5 次，全域計數（通道後的來源都是 127.0.0.1，不用 IP）


def pin() -> str:
    return os.environ.get("JOB_RAG_OWNER_PIN", "")


class Owner:
    def __init__(self, clock=time.time):
        self.clock, self.key, self.fails = clock, secrets.token_bytes(32), deque()

    @property
    def enabled(self) -> bool:
        return bool(pin())

    def _sig(self, body: str) -> str:
        return hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()

    def login(self, given) -> tuple[str, str | None]:
        """回 ("ok", cookie)、("bad", None)、("locked", None)。鎖定時連正確密碼也不收。"""
        now = self.clock()
        while self.fails and self.fails[0] <= now - FAIL_WINDOW:
            self.fails.popleft()
        if not self.enabled:
            return "bad", None
        if len(self.fails) >= FAIL_LIMIT:
            return "locked", None
        if not isinstance(given, str) or not hmac.compare_digest(given.encode("utf-8"), pin().encode("utf-8")):
            self.fails.append(now)
            return "bad", None
        body = f"{int(now + TTL)}.{secrets.token_hex(8)}"
        return "ok", f"{body}.{self._sig(body)}"

    def valid(self, cookie) -> bool:
        if not self.enabled or not isinstance(cookie, str):
            return False
        parts = cookie.split(".")
        if len(parts) != 3 or not parts[0].isascii() or not parts[0].isdigit():
            return False
        body = ".".join(parts[:2])
        return (hmac.compare_digest(parts[2].encode("utf-8"), self._sig(body).encode()) and int(parts[0]) > self.clock())

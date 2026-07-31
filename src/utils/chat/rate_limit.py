from collections import deque
import time


class RateLimiter:
    """
    滑动窗口限流器

    每个实例限制一个 session
    """

    def __init__(self, max_calls: int = 3, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls = deque()

    def allow(self) -> bool:
        """
        当前是否允许发送
        """

        now = time.monotonic()

        # 删除过期记录
        while self.calls and now - self.calls[0] > self.window_seconds:
            self.calls.popleft()

        if len(self.calls) >= self.max_calls:
            return False

        self.calls.append(now)
        return True

    def remaining(self) -> int:
        """
        剩余次数
        """

        now = time.monotonic()

        while self.calls and now - self.calls[0] > self.window_seconds:
            self.calls.popleft()

        return self.max_calls - len(self.calls)

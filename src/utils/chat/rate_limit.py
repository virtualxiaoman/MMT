from collections import deque
import time


class RateLimiter:
    """
    滑动窗口限流器
    """

    def __init__(self, max_calls: int = 3, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls = deque()

    def _cleanup(self) -> None:
        """删除过期记录"""
        now = time.monotonic()
        while self.calls and now - self.calls[0] >= self.window_seconds:
            self.calls.popleft()

    def allow(self) -> bool:
        """
        是否允许发送，不会记录发送。
        """
        self._cleanup()
        return len(self.calls) < self.max_calls

    def record(self) -> None:
        """
        记录一次成功发送。
        """
        self._cleanup()
        self.calls.append(time.monotonic())

    def remaining(self) -> int:
        """
        剩余发送次数。
        """
        self._cleanup()
        return self.max_calls - len(self.calls)

    def clear(self) -> None:
        """
        清空记录。
        """
        self.calls.clear()

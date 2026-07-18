from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.QQ.QQutils.msg.chat_session import MessageContext


class ReplyTrigger(Enum):
    """回复触发原因。"""
    TIMEOUT = auto()  # 超时
    MAX_PENDING = auto()  # 消息达到上限


class ReplyScheduler:
    """
    一个 Session 一个回复调度器。

    工作流程：

        收到消息
            ↓
        on_new_message(ctx)
            ↓
        更新：
            - 最新消息上下文
            - 消息计数
            - 最后一条消息时间
            ↓
        若当前没有等待任务，则创建一个后台 Task
            ↓
        _reply_loop() 持续检查：
            - 是否累计收到 MAX_PENDING 条消息
            - 或距离最后一条消息超过 WAIT_SECONDS
            ↓
        满足任一条件后调用 callback（ChatSession._reply）
            ↓
        重置状态，等待下一轮消息

    整个 Session 同时只会存在一个等待 Task。
    """
    WAIT_SECONDS = 5  # 最后一条消息静默多少秒后回复
    MAX_PENDING = 3  # 连续收到多少条消息立即回复
    CHECK_INTERVAL = 0.2  # 后台 Task 检查间隔

    def __init__(self, callback: Callable[[MessageContext, ReplyTrigger], Awaitable[None]]):
        self.callback = callback  # 回复时真正执行的回调（ChatSession._reply）
        self.reply_task: asyncio.Task | None = None  # 当前等待回复的后台 Task,None 表示当前没有等待中的回复任务

        self.pending_count = 0  # 自上次回复以来累计收到的消息数量
        self.last_message_time = 0.0  # 最后一条消息到达的时间（time.monotonic()）

        self.latest_ctx = None  # 保存最新收到消息对应的上下文,回复时使用最新的上下文进行处理

    async def on_new_message(self, ctx: MessageContext) -> None:
        """
        收到一条新消息时调用。
        每收到一条消息都会：
            1. 保存最新 ctx
            2. 消息计数 +1
            3. 更新时间
            4. 若当前没有等待 Task，则启动一个
        """
        self.latest_ctx = ctx
        self.pending_count += 1
        self.last_message_time = time.monotonic()

        if self.reply_task is None:
            self.reply_task = asyncio.create_task(self._reply_loop())

    async def _reply_loop(self) -> None:
        """
        后台等待回复时机。
        每隔 CHECK_INTERVAL 秒检查一次：
            ① 是否累计收到 MAX_PENDING 条消息；
            ② 是否已经静默 WAIT_SECONDS 秒。
        任一条件满足即触发回复。
        """
        try:
            while True:
                await asyncio.sleep(self.CHECK_INTERVAL)

                if self.pending_count >= self.MAX_PENDING:
                    trigger = ReplyTrigger.MAX_PENDING
                    break

                idle = time.monotonic() - self.last_message_time
                if idle >= self.WAIT_SECONDS:
                    trigger = ReplyTrigger.TIMEOUT
                    break

            await self.callback(self.latest_ctx, trigger)  # 对应ChatSession的_handle_reply

        finally:
            self.pending_count = 0
            self.reply_task = None

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from src.QQ.QQutils.msg.msg_wrapper import SendMessageBuilder
from src.QQ.QQutils.msg.reply_model import (
    ReplyDeliveryResult,
    ReplyOutcome,
    ReplyPart,
    ReplyPartKind,
)
from src.QQ.QQutils.res.history_storage import HistoryLogger

if TYPE_CHECKING:
    from src.QQ.QQutils.msg.chat_session import MessageContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class EmojiDeciderLike(Protocol):
    """表情决策器需要提供的最小接口。"""

    def get_emoji_path(self, text: str, p: float = 0.5) -> str | bool:
        ...


class VoiceDeciderLike(Protocol):
    """语音决策器需要提供的最小接口。"""

    def match(self, user_query: str, threshold: float = 0.712) -> str | bool:
        ...


class ReplyComposer:
    """将 AI 回复转换为一组按顺序发送的消息部件。"""

    def __init__(
            self,
            emoji_decider: EmojiDeciderLike | None,
            *,
            emoji_probability: float = 0.2,
            voice_decider: VoiceDeciderLike | None = None,
            voice_dir: Path | None = None,
    ):
        if not 0 <= emoji_probability <= 1:
            raise ValueError("emoji_probability 必须在 0 到 1 之间")

        self.emoji_decider = emoji_decider
        self.emoji_probability = emoji_probability
        self.voice_decider = voice_decider
        self.voice_dir = Path(voice_dir) if voice_dir else None

    def compose(self, ai_reply: str) -> list[ReplyPart]:
        """组装文本、表情和可选语音，文本始终放在第一位。"""

        parts = [
            ReplyPart(
                kind=ReplyPartKind.TEXT,
                content=ai_reply,
            )
        ]
        self._append_emoji_part(parts, ai_reply)
        self._append_voice_part(parts, ai_reply)
        return parts

    def _append_emoji_part(self, parts: list[ReplyPart], ai_reply: str) -> None:
        if self.emoji_decider is None:
            return

        try:
            emoji_path = self.emoji_decider.get_emoji_path(
                ai_reply,
                p=self.emoji_probability,
            )
        except Exception:
            logger.exception("表情决策失败，本轮只发送文本")
            return

        if not emoji_path:
            return

        path = Path(str(emoji_path))
        if not path.exists():
            logger.warning("表情文件不存在，跳过图片回复: %s", path)
            return

        parts.append(
            ReplyPart(
                kind=ReplyPartKind.IMAGE,
                content=path.stem,
                file=path,
            )
        )

    def _append_voice_part(self, parts: list[ReplyPart], ai_reply: str) -> None:
        if self.voice_decider is None or self.voice_dir is None:
            return

        try:
            voice_name = self.voice_decider.match(ai_reply)
        except Exception:
            logger.exception("语音决策失败，本轮不发送语音")
            return

        if not voice_name:
            return

        voice_path = self.voice_dir / str(voice_name)
        if not voice_path.exists():
            logger.warning("语音文件不存在，跳过语音回复: %s", voice_path)
            return

        parts.append(
            ReplyPart(
                kind=ReplyPartKind.RECORD,
                content=voice_path.stem,
                file=voice_path,
            )
        )


class ReplyRecorder:
    """把已经成功交付的消息部件批量写入历史记录。"""

    def __init__(
            self,
            history_logger: HistoryLogger,
            send_builder: SendMessageBuilder,
    ):
        self.history_logger = history_logger
        self.send_builder = send_builder

    def record(self, delivery: ReplyDeliveryResult) -> int:
        """只记录发送成功的部件，返回实际写入的消息数量。"""

        wrappers = [
            self.send_builder.from_delivered_part(item)
            for item in delivery.delivered
        ]
        return self.history_logger.append_sends(wrappers)


class ReplyService:
    """协调回复组装、网络发送、历史记录和限流。"""

    def __init__(
            self,
            composer: ReplyComposer,
            recorder: ReplyRecorder,
    ):
        self.composer = composer
        self.recorder = recorder

    async def respond(self, ctx: MessageContext, ai_reply: str) -> ReplyOutcome:
        """
        完成一次完整回复。

        部分发送失败时仍会记录已经成功的消息，保证用户可见内容与历史尽量一致。
        """

        parts = self.composer.compose(ai_reply)
        delivery = await ctx.msg_sender.send_parts(parts)

        recorded_count = 0
        record_error = None
        rate_recorded = False

        if delivery.sent_any:
            try:
                recorded_count = self.recorder.record(delivery)
            except Exception as exc:
                record_error = f"{type(exc).__name__}: {exc}"
                logger.exception("回复历史写入失败，已发送消息不会被重复发送")

            ctx.session.rate_limiter.record()
            rate_recorded = True

        if delivery.failures:
            logger.warning(
                "回复存在失败部件: delivered=%d, failed=%d",
                len(delivery.delivered),
                len(delivery.failures),
            )

        return ReplyOutcome(
            delivery=delivery,
            recorded_count=recorded_count,
            record_error=record_error,
            rate_recorded=rate_recorded,
        )

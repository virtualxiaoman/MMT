from __future__ import annotations

import random
import asyncio
import logging
from dataclasses import dataclass
from typing import Union

from ncatbot.core import BotClient, GroupMessageEvent, PrivateMessageEvent, GroupMessage, PrivateMessage

from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper, SendMessageBuilder
from src.QQ.QQutils.msg.pipeline import ChatPipeline
from src.QQ.QQutils.msg.reply_service import ReplyComposer, ReplyRecorder, ReplyService
from src.QQ.QQutils.msg.send_msg import MessageSender
from src.QQ.QQutils.res.history_loader import HistoryLoader
from src.QQ.QQutils.res.history_storage import HistoryLogger
from src.config.QQ_bot_info_loader import BotConfig
from src.config.QQ_reply_settings import QQReplySettings
from src.utils.chat.decider.emoji_decider import EmojiDecider
from src.utils.chat.decider.reply_decider import ReplyDecider, ReplyDecisionData
from src.utils.chat.history.manage_summary import SummaryGenerator, SummaryManager
from src.utils.chat.llm.run_prompt import PromptRunner
from src.utils.chat.prompt.load_prompt import RoleLoader
from src.utils.chat.rate_limit import RateLimiter
from src.utils.chat.reply_scheduler import ReplyScheduler, ReplyTrigger
from src.utils.tools.res.emoji_detector import EmojiDetector
from src.utils.tools.res.rand_pic import RandomPicture

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class MessageContext:
    bot: BotClient
    msg: Union[GroupMessage, PrivateMessage]
    session: "ChatSession"
    msg_sender: "MessageSender"
    recv_msg_wrapper: "RecvMessageWrapper"
    config: "BotConfig"
    tool_text: str
    is_private: bool
    session_id: str


class ChatSession:
    def __init__(
            self,
            session_id: str,
            is_private: bool = False,
            config: BotConfig | None = None,
            emoji_detector: EmojiDetector | None = None,
    ):
        self.session_id = session_id
        self.is_private = is_private
        # self.llm_chater = ChatDSAPI()  # 默认deepseek
        self.reply_decider = ReplyDecider(config)
        self.emoji_decider = EmojiDecider()
        # self.llm_chater.init_role(config.name_zh)
        self.random_picture_provider = RandomPicture(config.paths.random_picture_dirs)
        self.qq_reply_settings = QQReplySettings(config.bot_id)
        # 从 bot YAML 读取表情目录；BotManager 创建共享实例后传入，避免每个会话开新连接。
        self.emoji_detector = emoji_detector or EmojiDetector(config.paths.emoji_dir)
        self.reply_scheduler = ReplyScheduler(self._handle_reply)
        self.rate_limiter = RateLimiter(max_calls=3, window_seconds=60)  # 滑动窗口
        self.reply_service: ReplyService | None = None
        self.pipeline: ChatPipeline | None = None
        if config is not None:
            self._init_reply_service(config)
        logger.info(f"已为{'私聊' if is_private else '群聊'} {session_id} 初始化 AI 会话")

    def _init_reply_service(self, config: BotConfig) -> None:
        """初始化与会话绑定的历史记录器和回复服务。"""

        self.history_logger = HistoryLogger(config=config)
        self.send_builder = SendMessageBuilder(
            session_id=self.session_id,
            is_private=self.is_private,
            bot_id=str(config.bot_id),
            bot_name=config.name_zh,
        )

        composer = ReplyComposer(
            emoji_decider=self.emoji_decider,
            emoji_probability=0.2,
        )
        recorder = ReplyRecorder(
            history_logger=self.history_logger,
            send_builder=self.send_builder,
        )
        self.reply_service = ReplyService(
            composer=composer,
            recorder=recorder,
        )

    # async def get_reply(self, text: str) -> str:
    #     """调用 AI 生成回复"""
    #     try:
    #         # ChatDSAPI.one_chat 是同步的
    #         loop = asyncio.get_event_loop()
    #         return await loop.run_in_executor(None, self.llm_chater.one_chat, text)
    #     except Exception as e:
    #         logger.error(f"AI 生成回复失败: {e}")
    #         return "呜... 脑子转不过来了..."

    async def generate_reply(self, ctx: MessageContext, text: str) -> str:
        """
        调用 ChatPipeline 生成回复
        """
        try:
            loop = asyncio.get_running_loop()
            pipeline = self._get_pipeline(ctx)
            reply = await loop.run_in_executor(None, pipeline.chat, text)
            return reply
        except Exception:
            logger.exception("AI 生成回复失败")
            return f"呜... {ctx.config.name_zh}有点晕晕的..."

    def _get_pipeline(self, ctx: MessageContext) -> ChatPipeline:
        """会话内复用 ChatPipeline/SummaryManager，避免每次回复都重建 LLM client 与摘要状态。"""
        if self.pipeline is None:
            runner = PromptRunner()
            generator = SummaryGenerator(runner)
            manager = SummaryManager(
                bot_id=ctx.config.bot_id,
                is_private=ctx.is_private,
                session_id=ctx.session_id,
                generator=generator,
            )
            self.pipeline = ChatPipeline(
                bot_id=ctx.config.bot_id,
                is_private=ctx.is_private,
                session_id=ctx.session_id,
                system_prompt=RoleLoader.load(ctx.config.name_en),
                name_en=ctx.config.name_en,
                summary_manager=manager,
                name_zh=ctx.config.name_zh,
            )
        return self.pipeline

    async def _handle_reply(self, ctx: MessageContext, trigger: ReplyTrigger) -> None:
        """
        ReplyScheduler 回调，只负责判断和编排，不处理具体媒体发送细节。
        """

        logger.info("回复调度触发，原因: %s", trigger.name)
        history_msg = HistoryLoader.load_last(bot_id=ctx.config.bot_id, is_private=ctx.is_private,
                                              session_id=ctx.session_id, max_lines=20)

        decision = await self._should_reply(ctx, history_msg)
        if not await self._decision_to_bool(decision):
            logger.info("决定不回复这条消息: %s", ctx.recv_msg_wrapper.tool_msg[:10])
            return

        ai_reply = await self.generate_reply(ctx=ctx, text=ctx.recv_msg_wrapper.llm_msg)
        if self.reply_service is None:
            logger.error("回复服务未初始化，无法发送 AI 回复")
            return

        outcome = await self.reply_service.respond(ctx=ctx, ai_reply=ai_reply)
        logger.info(
            "回复处理完成: delivered=%d, failed=%d, recorded=%d, rate_recorded=%s",
            outcome.delivered_count,
            outcome.failed_count,
            outcome.recorded_count,
            outcome.rate_recorded,
        )
        if outcome.record_error:
            logger.error("回复历史记录失败: %s", outcome.record_error)

    async def _should_reply(self, ctx: MessageContext, history_msg: str) -> ReplyDecisionData:
        """
        判定是否回复：看回复类型，私聊默认回复，群聊由 decider 判定
        """
        if ctx.is_private:
            return ReplyDecisionData(
                needs_reply="required",
                reason="私聊默认回复"
            )  # 私聊除非被拉黑，不然就默认回复
        image_files = ctx.recv_msg_wrapper.image_files
        # 检查有多少张图片，如果只有一张才进行表情包检测
        if len(image_files) == 1:
            is_emoji = ctx.session.emoji_detector.is_emoji_file(image_files[0])
            logger.debug("%s is emoji: %s", image_files, is_emoji)
        elif len(ctx.recv_msg_wrapper.image_urls) == 1:
            # 图片落盘失败时退回 URL 检测，保证表情包仍然可以被识别。
            is_emoji = ctx.session.emoji_detector.is_emoji(ctx.recv_msg_wrapper.image_urls[0])
            logger.debug("%s is emoji: %s", ctx.recv_msg_wrapper.image_urls, is_emoji)
        else:
            is_emoji = False
        if is_emoji:
            return ReplyDecisionData(
                needs_reply="skip",
                reason="只是表情包，不回复"
            )  # 如果是表情包就不回复
        # 群聊还要由模型判定是否回复
        return ctx.session.reply_decider.check_if_should_reply(ctx.recv_msg_wrapper.llm_msg, history_msg)

    @staticmethod
    async def _decision_to_bool(decision: ReplyDecisionData) -> bool:
        """
        将 ReplyDecisionData 转换为最终是否回复。
        """
        if decision.needs_reply == "required":
            return True
        if decision.needs_reply == "skip":
            return False
        return random.random() < max(0.0, min(1.0, decision.probability))

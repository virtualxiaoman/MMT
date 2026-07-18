from __future__ import annotations

import random
import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Union

from ncatbot.core import BotClient, GroupMessageEvent, PrivateMessageEvent, GroupMessage, PrivateMessage

from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper, SendMessageBuilder
from src.QQ.QQutils.msg.pipeline import ChatPipeline
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
from src.utils.chat.reply_scheduler import ReplyScheduler, ReplyTrigger
from src.utils.chat.role_chat import ChatDSAPI
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
    def __init__(self, session_id: str, is_private: bool = False, config: BotConfig | None = None):
        self.session_id = session_id
        self.is_private = is_private
        # self.llm_chater = ChatDSAPI()  # 默认deepseek
        self.reply_decider = ReplyDecider(config)
        self.emoji_decider = EmojiDecider()
        # self.llm_chater.init_role(config.name_zh)
        self.random_picture_provider = RandomPicture(config.paths.random_picture_dirs)
        self.qq_reply_settings = QQReplySettings(config.bot_id)
        self.emoji_detector = EmojiDetector(
            emoji_dir=r"D:\Users\Administrator\Desktop\Emoji\LuoTianyi",  # todo
        )
        self.reply_scheduler = ReplyScheduler(self._handle_reply)
        logger.info(f"已为{'私聊' if is_private else '群聊'} {session_id} 初始化 AI 会话")

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
            func = partial(
                chat_pipeline,
                ctx=ctx,
                query=text
            )

            reply = await loop.run_in_executor(
                None,
                func,
            )

            return reply

        except Exception:
            logger.exception("AI 生成回复失败")
            return "呜... 脑子转不过来了..."

    async def _handle_reply(
            self,
            ctx: MessageContext,
            trigger: ReplyTrigger,
    ) -> None:
        """
        ReplyScheduler 回调。

        这里以后放真正回复逻辑。
        """
        print(f"触发原因: {trigger}")
        # =========================
        # 4. 判断是否回复
        # =========================
        history_msg = HistoryLoader.load_last(bot_id=ctx.config.bot_id, is_private=ctx.is_private,
                                              session_id=ctx.session_id, max_lines=20)

        decision = await self._should_reply(ctx, history_msg)
        if not await self._decision_to_bool(decision):
            logger.info(f"决定不回复这条消息{ctx.recv_msg_wrapper.tool_msg[:10]}")
            return

        # =========================
        # 5. 回复
        # =========================
        ai_reply = await ctx.session.generate_reply(ctx=ctx, text=ctx.recv_msg_wrapper.llm_msg)  # 生成回复
        emoji_path = ctx.session.emoji_decider.get_emoji_path(ai_reply, p=0.2)  # 表情包路径

        text_msg_id = await ctx.msg_sender.text(ai_reply)  # 先发送文本回复
        if emoji_path:
            image_msg_id = await ctx.msg_sender.image(emoji_path)  # 如果有表情路径，再发送表情
        else:
            image_msg_id = None
        # todo 语音回复

        # =========================
        # 6. 存储回复消息
        # =========================
        builder = SendMessageBuilder(ctx.recv_msg_wrapper.session_id, ctx.is_private,
                                     bot_id=str(ctx.config.bot_id), bot_name=ctx.config.name_zh)
        send_wrappers = list()
        send_wrappers.append(builder.text(message_id=text_msg_id, text=ai_reply))
        if image_msg_id:
            send_wrappers.append(builder.image(message_id=image_msg_id, file=emoji_path,
                                               content=Path(emoji_path).stem))

        history_logger = HistoryLogger(config=ctx.config)
        for send_wrapper in send_wrappers:
            history_logger.append_send(send_wrapper)  # 保存消息（LLMinput+人类可读）

    async def _should_reply(self, ctx: MessageContext, history_msg: str) -> ReplyDecisionData:
        """
        判定是否回复：看回复类型，私聊默认回复，群聊由 decider 判定
        """
        if ctx.is_private:
            return ReplyDecisionData(
                needs_reply="required",
                reason="私聊默认回复"
            )  # 私聊除非被拉黑，不然就默认回复
        image_url = ctx.recv_msg_wrapper.image_urls
        # print(f"[_should_reply] 图片数量：{len(image_url)}")
        # 检查有多少张图片，如果只有一张才进行表情包检测
        if len(image_url) == 1:
            is_emoji = ctx.session.emoji_detector.is_emoji(image_url[0])
            print(f"{image_url} is emoji: {is_emoji}")
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


def chat_pipeline(ctx: MessageContext, query: str):
    name_en = ctx.config.name_en
    bot_id = ctx.config.bot_id
    is_private = ctx.is_private
    session_id = ctx.session_id
    role_prompt = RoleLoader.load(name_en)
    runner = PromptRunner()
    generator = SummaryGenerator(runner)
    manager = SummaryManager(bot_id=bot_id, is_private=is_private, session_id=session_id, generator=generator)
    pipeline = ChatPipeline(bot_id=bot_id, is_private=is_private, session_id=session_id,
                            system_prompt=role_prompt, name_en=name_en, memory_manager=manager,
                            name_zh=ctx.config.name_zh)
    reply = pipeline.chat(query)
    print(reply)
    return reply

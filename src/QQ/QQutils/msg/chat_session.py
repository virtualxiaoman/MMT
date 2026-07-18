from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from typing import Union

from ncatbot.core import BotClient, GroupMessageEvent, PrivateMessageEvent, GroupMessage, PrivateMessage

from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper
from src.QQ.QQutils.msg.pipeline import ChatPipeline
from src.QQ.QQutils.msg.send_msg import MessageSender
from src.config.QQ_bot_info_loader import BotConfig
from src.config.QQ_reply_settings import QQReplySettings
from src.utils.chat.decider.emoji_decider import EmojiDecider
from src.utils.chat.decider.reply_decider import ReplyDecider
from src.utils.chat.history.manage_summary import SummaryGenerator, SummaryManager
from src.utils.chat.llm.run_prompt import PromptRunner
from src.utils.chat.prompt.load_prompt import RoleLoader
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
            emoji_dir=r"D:\Users\Administrator\Desktop\Emoji\LuoTianyi",
        )
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

    async def get_reply(
            self,
            ctx: MessageContext,
            text: str,
    ) -> str:
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

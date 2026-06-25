from dataclasses import dataclass
from typing import Union
from ncatbot.core import BotClient, GroupMessage, PrivateMessage, GroupMessageEvent, PrivateMessageEvent

import logging

from src.QQ.QQutils.msg.chat_session import ChatSession

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MessageSender:
    def __init__(self, bot: BotClient, msg: Union[GroupMessage, PrivateMessage]):
        self.bot = bot
        self.msg = msg
        self.is_private = isinstance(msg, PrivateMessage)

    # 文本
    async def text(self, content: str):
        if self.is_private:
            await self.bot.api.post_private_msg(
                user_id=self.msg.user_id,
                text=content
            )
        else:
            await self.bot.api.post_group_msg(
                group_id=self.msg.group_id,
                text=content
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id} 的文本消息: {content}")

    # 图片
    async def image(self, path: str):
        if self.is_private:
            await self.bot.api.post_private_msg(
                user_id=self.msg.user_id,
                image=path
            )
        else:
            await self.bot.api.post_group_msg(
                group_id=self.msg.group_id,
                image=path
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id}，图片路径为: {path}")

    # 语音
    async def record(self, path: str):
        if self.is_private:
            await self.bot.api.send_private_record(
                user_id=self.msg.user_id,
                file=path
            )
        else:
            await self.bot.api.send_group_record(
                group_id=self.msg.group_id,
                file=path
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id}，语音路径为: {path}")


@dataclass
class MessageContext:
    bot: BotClient
    msg: Union[GroupMessage, PrivateMessage]
    session: "ChatSession"
    msg_sender: "MessageSender"

    user_raw_text: str
    is_private: bool
    session_id: str

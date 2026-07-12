from typing import Union
from ncatbot.core import BotClient, GroupMessage, PrivateMessage

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MessageSender:
    def __init__(self, bot: BotClient, msg: Union[GroupMessage, PrivateMessage]):
        self.bot = bot
        self.msg = msg
        self.is_private = isinstance(msg, PrivateMessage)

    # 文本
    async def text(self, content: str) -> str:
        if self.is_private:
            message_id = await self.bot.api.post_private_msg(
                user_id=self.msg.user_id,
                text=content
            )
        else:
            message_id = await self.bot.api.post_group_msg(
                group_id=self.msg.group_id,
                text=content
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id} 的文本消息: {content}")
        return message_id

    # 图片
    async def image(self, path: str) -> str:
        if self.is_private:
            message_id = await self.bot.api.post_private_msg(
                user_id=self.msg.user_id,
                image=path
            )
        else:
            message_id = await self.bot.api.post_group_msg(
                group_id=self.msg.group_id,
                image=path
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id}，图片路径为: {path}")
        return message_id

    # 语音
    async def record(self, path: str) -> str:
        if self.is_private:
            message_id = await self.bot.api.send_private_record(
                user_id=self.msg.user_id,
                file=path
            )
        else:
            message_id = await self.bot.api.send_group_record(
                group_id=self.msg.group_id,
                file=path
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id}，语音路径为: {path}")
        return message_id



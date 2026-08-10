import logging

from ncatbot.core.client import BotClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MessageSender:
    def __init__(self, bot: BotClient, session_id: str, is_private: bool):
        self.bot = bot
        self.session_id = session_id
        self.is_private = is_private

    # 获取本次发送使用的目标会话
    def _resolve_target(self, session_id: str | None = None, is_private: bool | None = None) -> tuple[str, bool]:
        return (session_id if session_id is not None else self.session_id,
                is_private if is_private is not None else self.is_private)

    # 文本
    async def text(self, content: str, session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.post_private_msg(user_id=session_id, text=content)
        else:
            message_id = await self.bot.api.post_group_msg(group_id=session_id, text=content)
        logger.info(f"已回复{'用户' if self.is_private else '群'} {session_id} 的文本消息: {content}")
        return message_id

    # 图片
    async def image(self, path: str, session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.post_private_msg(user_id=session_id, image=path)
        else:
            message_id = await self.bot.api.post_group_msg(group_id=session_id, image=path)
        logger.info(f"已回复{'用户' if self.is_private else '群'} {session_id}，图片路径为: {path}")
        return message_id

    # 语音
    async def record(self, path: str, session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.send_private_record(user_id=session_id, file=path)
        else:
            print(path)
            message_id = await self.bot.api.send_group_record(group_id=session_id, file=path)
        logger.info(f"已回复{'用户' if self.is_private else '群'} {session_id}，语音路径为: {path}")
        return message_id

    # 文件
    async def file(self, path: str, name: str | None = None,
                   session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.send_private_file(user_id=session_id, file=path, name=name)
        else:
            message_id = await self.bot.api.send_group_file(group_id=session_id, file=path, name=name)
        logger.info(f"已回复{'用户' if self.is_private else '群'} {session_id}，"
                    f"文件路径为: {path}，文件名: {name}" if name else "")
        return message_id

# class MessageSender:
#     def __init__(self, bot: BotClient, msg: Union[GroupMessage, PrivateMessage]):
#         self.bot = bot
#         self.msg = msg
#         self.is_private = isinstance(msg, PrivateMessage)
#
#     # 文本
#     async def text(self, content: str) -> str:
#         if self.is_private:
#             message_id = await self.bot.api.post_private_msg(
#                 user_id=self.msg.user_id,
#                 text=content
#             )
#         else:
#             message_id = await self.bot.api.post_group_msg(
#                 group_id=self.msg.group_id,
#                 text=content
#             )
#         logger.info(f"已回复{'用户' if self.is_private else '群'} "
#                     f"{self.msg.user_id if self.is_private else self.msg.group_id} 的文本消息: {content}")
#         return message_id
#
#     # 图片
#     async def image(self, path: str) -> str:
#         if self.is_private:
#             message_id = await self.bot.api.post_private_msg(
#                 user_id=self.msg.user_id,
#                 image=path
#             )
#         else:
#             message_id = await self.bot.api.post_group_msg(
#                 group_id=self.msg.group_id,
#                 image=path
#             )
#         logger.info(f"已回复{'用户' if self.is_private else '群'} "
#                     f"{self.msg.user_id if self.is_private else self.msg.group_id}，图片路径为: {path}")
#         return message_id
#
#     # 语音
#     async def record(self, path: str) -> str:
#         if self.is_private:
#             message_id = await self.bot.api.send_private_record(
#                 user_id=self.msg.user_id,
#                 file=path
#             )
#         else:
#             message_id = await self.bot.api.send_group_record(
#                 group_id=self.msg.group_id,
#                 file=path
#             )
#         logger.info(f"已回复{'用户' if self.is_private else '群'} "
#                     f"{self.msg.user_id if self.is_private else self.msg.group_id}，语音路径为: {path}")
#         return message_id

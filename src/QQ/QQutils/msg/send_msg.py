import logging
from collections.abc import Iterable

from ncatbot.core.client import BotClient

from src.QQ.QQutils.msg.reply_model import (
    DeliveredPart,
    DeliveryFailure,
    ReplyDeliveryResult,
    ReplyPart,
    ReplyPartKind,
)

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
        if not content or not content.strip():
            logger.warning(f"文本内容为空，取消发送 (session_id={session_id}, is_private={is_private})")
            return ""  # 返回空字符串表示未发送，也可以改为 raise ValueError
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.post_private_msg(user_id=session_id, text=content)
        else:
            message_id = await self.bot.api.post_group_msg(group_id=session_id, text=content)
        logger.info(f"已回复{'用户' if is_private else '群'} {session_id} 的文本消息: {content}")
        return message_id

    # 图片
    async def image(self, path: str, session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.post_private_msg(user_id=session_id, image=path)
        else:
            message_id = await self.bot.api.post_group_msg(group_id=session_id, image=path)
        logger.info(f"已回复{'用户' if is_private else '群'} {session_id}，图片路径为: {path}")
        return message_id

    # 语音
    async def record(self, path: str, session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.send_private_record(user_id=session_id, file=path)
        else:
            message_id = await self.bot.api.send_group_record(group_id=session_id, file=path)
        logger.info(f"已回复{'用户' if is_private else '群'} {session_id}，语音路径为: {path}")
        return message_id

    # 文件
    async def file(self, path: str, name: str | None = None,
                   session_id: str | None = None, is_private: bool | None = None) -> str:
        session_id, is_private = self._resolve_target(session_id, is_private)
        if is_private:
            message_id = await self.bot.api.send_private_file(user_id=session_id, file=path, name=name)
        else:
            message_id = await self.bot.api.send_group_file(group_id=session_id, file=path, name=name)
        logger.info(f"已回复{'用户' if is_private else '群'} {session_id}，"
                    f"文件路径为: {path}，文件名: {name}" if name else "")
        return message_id

    # 根据回复部件类型调用对应的底层发送接口
    async def send_part(self, part: ReplyPart) -> str:
        """
        发送单个回复部件。

        该方法只负责类型路由，不处理历史记录和限流。
        """

        if part.kind is ReplyPartKind.TEXT:
            return await self.text(part.content)

        if part.kind is ReplyPartKind.IMAGE:
            if part.file is None:
                raise ValueError("图片回复部件缺少 file 字段")
            return await self.image(str(part.file))

        if part.kind is ReplyPartKind.RECORD:
            if part.file is None:
                raise ValueError("语音回复部件缺少 file 字段")
            return await self.record(str(part.file))

        raise ValueError(f"不支持的回复部件类型: {part.kind}")

    # 按顺序发送整组回复部件，并收集部分成功结果
    async def send_parts(
            self,
            parts: Iterable[ReplyPart],
            *,
            stop_on_error: bool = False,
    ) -> ReplyDeliveryResult:
        """
        发送一组回复部件。

        默认不会因为某一个部件失败而停止后续发送，已经成功的部件仍会保留在结果中。
        """

        delivered: list[DeliveredPart] = []
        failures: list[DeliveryFailure] = []

        for part in tuple(parts):
            try:
                message_id = await self.send_part(part)
            except Exception as exc:
                logger.warning(
                    "回复部件发送失败: kind=%s, error=%s",
                    part.kind.value,
                    exc,
                    exc_info=True,
                )
                failures.append(
                    DeliveryFailure(
                        part=part,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
                if stop_on_error:
                    break
                continue

            if message_id is None or message_id == "":
                failures.append(
                    DeliveryFailure(
                        part=part,
                        error="平台未返回有效 message_id",
                    )
                )
                continue

            delivered.append(
                DeliveredPart(
                    part=part,
                    message_id=str(message_id),
                )
            )

        return ReplyDeliveryResult(
            delivered=tuple(delivered),
            failures=tuple(failures),
        )


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

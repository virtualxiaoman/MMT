from __future__ import annotations

import time
from typing import Any

from ncatbot.core import BotClient, GroupMessage, PrivateMessage

from src.utils.chat.img_describer import ImageDescriber


# 应该继承同一个类以便一起管理
class RecvMessageWrapper:
    """
    将原始消息标准化
    """

    def __init__(self, msg):
        self.raw_msg = msg
        self.data = self._parse_message(msg)

        self.image_describer = ImageDescriber()

        self.processed = False  # 标识有没有对多模态数据进行处理

    def _parse_message(self, msg) -> dict:
        """
        将原始消息转为统一JSON结构
        """
        is_private = isinstance(msg, PrivateMessage)  # 是否是私聊
        user_id = str(msg.user_id)  # 发送者(用户)id
        session_id = (str(msg.user_id) if is_private else str(msg.group_id))  # [会话id] 私聊使用对话者id，群聊使用群聊id
        sender = getattr(msg, "sender", None)
        nickname = getattr(sender, "nickname", "")  # 目前没遇到没有nickname的情况
        reply_message_id = None

        segments = []
        for index, seg in enumerate(msg.message):
            seg_type = seg.__class__.__name__
            # Reply
            if seg_type == "Reply":
                reply_message_id = str(seg.id)
                continue
            # Text
            elif seg_type == "Text" or seg_type == "PlainText":
                content = str(seg.text)
                segments.append({
                    "index": len(segments),
                    "type": "text",
                    "content": content
                })
            # At
            elif seg_type == "At":
                segments.append({
                    "index": len(segments),
                    "type": "at",
                    "qq_id": str(seg.qq)
                })
            # Face
            elif seg_type == "Face":
                segments.append({
                    "index": len(segments),
                    "type": "qq_face",
                    "face_id": str(seg.id),
                    "content": getattr(seg, "faceText", "")  # todo: 经测试，始终是[表情]，后续应该修改为查表，如下：
                    # https://koishi.js.org/QFace/#/qqnt
                    # https://github.com/koishijs/QFace
                    # https://koishi.js.org/QFace/assets/qq_emoji/_index.json
                })
            # Image
            elif seg_type == "Image":
                summary = getattr(seg, "summary", "")
                # QQ商城表情
                if summary:
                    segments.append({
                        "index": len(segments),
                        "type": "qq_emoji",
                        "summary": summary,
                        "content": summary,
                        "url": getattr(seg, "url", ""),
                        "file": None
                    })
                # 图片
                else:
                    segments.append({
                        "index": len(segments),
                        "type": "image",
                        "summary": "",
                        "content": None,  # 后续OCR/VLM填写
                        "url": getattr(seg, "url", ""),
                        "file": None
                    })
            # todo 暂不支持文件
        return {
            "timestamp": getattr(msg, "time", int(time.time())),  # 时间戳，msg是有time属性的，这里只是以防万一
            "message_id": str(msg.message_id),
            "reply_message_id": reply_message_id,
            "user_id": user_id,
            "user_nickname": nickname,
            "is_private": is_private,
            "session_id": session_id,
            "raw_message": str(msg),
            "segments": segments
        }

    # 处理消息内容：图片转描述
    def process_content(self):
        self.fill_image_content()  # todo: 目前仅图片，后续应该支持语音等
        self.processed = True

    # ===== 图片内容描述 =====
    def fill_image_content(self) -> None:
        """
        使用VLM补全图片content
        """
        for seg in self.data["segments"]:
            if seg["type"] == "image" or seg["type"] == "qq_emoji":
                try:
                    seg["content"] = self.image_describer.describe_img(seg["url"])
                except Exception as e:
                    print(f"[MessageWrapper] 图片识别失败: {e}")
                    seg["content"] = None

    @property
    def json(self) -> dict:
        """
        获取完整JSON
        """
        return self.data

    @property
    def user_id(self) -> str:
        return self.data["user_id"]

    @property
    def session_id(self) -> str:
        return self.data["session_id"]

    @property
    def is_private(self) -> bool:
        return self.data["is_private"]

    @property
    def reply_message_id(self) -> str | None:
        return self.data["reply_message_id"]

    @property
    def segments(self) -> list:
        return self.data["segments"]

    @property
    def timestamp(self) -> int:
        return self.data["timestamp"]

    @property
    def user_nickname(self) -> str:
        return self.data["user_nickname"]

    @property
    def text_msg(self) -> str:
        """
        提取适合LLM阅读的文本
        """
        if not self.processed:
            self.process_content()
        result = []
        for seg in self.segments:
            seg_type = seg["type"]
            if seg_type == "text":
                result.append(seg["content"])
            elif seg_type == "emoji":
                result.append(seg["content"])
            elif seg_type == "qq_face":
                result.append(seg["content"])
            elif seg_type == "qq_emoji":
                result.append(seg["content"])
            elif seg_type == "at":
                result.append(f'@{seg["qq_id"]}')
            elif seg_type == "image":
                if seg["content"]:
                    result.append(f'【图片内容】：{seg["content"]}')
                else:
                    result.append("[图片]")

        content = " ".join(result)
        time_str = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(self.timestamp)
        )
        return (
            f"[{time_str}] "
            f"{self.user_nickname}："
            f"{content}"
        )

    @property
    def tool_msg(self) -> str:
        """
        提取传入工具类的文本
        """
        result = []
        for seg in self.segments:
            seg_type = seg["type"]
            if seg_type == "text":
                result.append(seg["content"])
            elif seg_type == "at":
                result.append(f'@{seg["qq_id"]}')

        content = " ".join(result)
        return content

    @property
    def image_urls(self) -> list[str]:
        """
        获取所有图片URL
        """
        return [
            seg["url"]
            for seg in self.segments
            if seg["type"] == "image"
        ]

    @property
    def has_image(self) -> bool:
        return any(
            seg["type"] == "image"
            for seg in self.segments
        )

    @property
    def has_at(self) -> bool:
        return any(
            seg["type"] == "at"
            for seg in self.segments
        )


class SendMessageWrapper:
    """
    发送消息标准化对象。

    与 RecvMessageWrapper 保持 data 结构一致，
    方便统一存储、统一处理。
    """

    def __init__(
            self,
            *,
            message_id: str,
            session_id: str,
            is_private: bool,
            user_id: str,
            user_nickname: str,
            segments: list,
            reply_message_id: str | None = None,
            timestamp: int | None = None,
            raw_message: str | None = None,
    ):
        self.raw_msg = None

        self.data = {
            "timestamp": timestamp or int(time.time()),
            "message_id": str(message_id),
            "reply_message_id": reply_message_id,
            "user_id": str(user_id),
            "user_nickname": user_nickname,
            "is_private": is_private,
            "session_id": str(session_id),
            "raw_message": raw_message,
            "segments": segments,
        }

        # Builder已经填好了，不需要再次处理
        self.processed = True

    @property
    def json(self) -> dict:
        return self.data

    @property
    def message_id(self):
        return self.data["message_id"]

    @property
    def user_id(self):
        return self.data["user_id"]

    @property
    def session_id(self):
        return self.data["session_id"]

    @property
    def is_private(self):
        return self.data["is_private"]

    @property
    def reply_message_id(self):
        return self.data["reply_message_id"]

    @property
    def segments(self):
        return self.data["segments"]

    @property
    def timestamp(self):
        return self.data["timestamp"]

    @property
    def user_nickname(self):
        return self.data["user_nickname"]

    @property
    def text_msg(self):
        """
        与RecvMessageWrapper保持一致。
        """

        result = []

        for seg in self.segments:
            seg_type = seg["type"]

            if seg_type == "text":
                result.append(seg["content"])

            elif seg_type == "qq_face":
                result.append(seg["content"])

            elif seg_type == "qq_emoji":
                result.append(seg["content"])

            elif seg_type == "at":
                result.append(f'@{seg["qq_id"]}')

            elif seg_type == "image":
                if seg["content"]:
                    result.append(f'【图片内容】：{seg["content"]}')
                else:
                    result.append("[图片]")

        content = " ".join(result)

        time_str = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(self.timestamp)
        )

        return (
            f"[{time_str}] "
            f"{self.user_nickname}："
            f"{content}"
        )


class SendMessageBuilder:
    """
    Builder负责根据发送内容构建SendMessageWrapper。
    """

    def __init__(
            self,
            recv_msg_wrapper,
            bot_id: str,
            bot_name: str = "Bot",
    ):
        self.recv = recv_msg_wrapper

        self.bot_id = str(bot_id)
        self.bot_name = bot_name

    # =======================
    # Text
    # =======================

    def text(
            self,
            message_id: str,
            text: str,
            reply_message_id: str | None = None,
    ) -> SendMessageWrapper:
        return SendMessageWrapper(
            message_id=message_id,
            session_id=self.recv.session_id,
            is_private=self.recv.is_private,
            user_id=self.bot_id,
            user_nickname=self.bot_name,
            reply_message_id=reply_message_id,
            segments=[
                {
                    "index": 0,
                    "type": "text",
                    "content": text,
                }
            ],
        )

    # =======================
    # Image
    # =======================

    def image(
            self,
            message_id: str,
            *,
            file: str | None = None,
            url: str = "",
            content: str | None = None,
            summary: str = "",
            reply_message_id: str | None = None,
    ) -> SendMessageWrapper:
        return SendMessageWrapper(
            message_id=message_id,
            session_id=self.recv.session_id,
            is_private=self.recv.is_private,
            user_id=self.bot_id,
            user_nickname=self.bot_name,
            reply_message_id=reply_message_id,
            segments=[
                {
                    "index": 0,
                    "type": "image",
                    "summary": summary,
                    "content": content,
                    "url": url,
                    "file": file,
                }
            ],
        )

    # =======================
    # QQ商城表情
    # =======================

    def qq_emoji(
            self,
            message_id: str,
            summary: str,
            *,
            file: str | None = None,
            url: str = "",
            content: str | None = None,
            reply_message_id: str | None = None,
    ) -> SendMessageWrapper:
        return SendMessageWrapper(
            message_id=message_id,
            session_id=self.recv.session_id,
            is_private=self.recv.is_private,
            user_id=self.bot_id,
            user_nickname=self.bot_name,
            reply_message_id=reply_message_id,
            segments=[
                {
                    "index": 0,
                    "type": "qq_emoji",
                    "summary": summary,
                    "content": content or summary,
                    "url": url,
                    "file": file,
                }
            ],
        )

    # =======================
    # At
    # =======================

    def at(
            self,
            message_id: str,
            qq_id: str,
            reply_message_id: str | None = None,
    ) -> SendMessageWrapper:
        return SendMessageWrapper(
            message_id=message_id,
            session_id=self.recv.session_id,
            is_private=self.recv.is_private,
            user_id=self.bot_id,
            user_nickname=self.bot_name,
            reply_message_id=reply_message_id,
            segments=[
                {
                    "index": 0,
                    "type": "at",
                    "qq_id": str(qq_id),
                }
            ],
        )

    # =======================
    # QQ Face
    # =======================

    def qq_face(
            self,
            message_id: str,
            face_id: str,
            content: str = "[表情]",
            reply_message_id: str | None = None,
    ) -> SendMessageWrapper:
        return SendMessageWrapper(
            message_id=message_id,
            session_id=self.recv.session_id,
            is_private=self.recv.is_private,
            user_id=self.bot_id,
            user_nickname=self.bot_name,
            reply_message_id=reply_message_id,
            segments=[
                {
                    "index": 0,
                    "type": "qq_face",
                    "face_id": str(face_id),
                    "content": content,
                }
            ],
        )

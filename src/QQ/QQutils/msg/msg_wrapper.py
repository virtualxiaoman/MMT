from __future__ import annotations

import time
from typing import Any

from ncatbot.core import BotClient, GroupMessage, PrivateMessage

from src.utils.chat.img_describer import ImageDescriber


class MessageWrapper:
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
        user_id = int(msg.user_id)  # 发送者(用户)id
        session_id = (int(msg.user_id) if is_private else int(msg.group_id))  # [会话id] 私聊使用对话者id，群聊使用群聊id
        sender = getattr(msg, "sender", None)
        nickname = getattr(sender, "nickname", "")  # 目前没遇到没有nickname的情况
        reply_message_id = None

        segments = []
        for index, seg in enumerate(msg.message):
            seg_type = seg.__class__.__name__
            # Reply
            if seg_type == "Reply":
                reply_message_id = int(seg.id)
                continue
            # Text
            elif seg_type == "Text":
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
                    "qq_id": int(seg.qq)
                })
            # Face
            elif seg_type == "Face":
                segments.append({
                    "index": len(segments),
                    "type": "qq_face",
                    "face_id": str(seg.id),
                    "content": getattr(seg, "faceText", "")  # todo: 经测试，始终是[表情]，后续应该修改为查表
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
            if seg["type"] != "image":
                continue
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
    def user_id(self) -> int:
        return self.data["user_id"]

    @property
    def session_id(self) -> int:
        return self.data["session_id"]

    @property
    def is_private(self) -> bool:
        return self.data["is_private"]

    @property
    def reply_message_id(self) -> int | None:
        return self.data["reply_message_id"]

    @property
    def segments(self) -> list:
        return self.data["segments"]

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
        return " ".join(result)

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

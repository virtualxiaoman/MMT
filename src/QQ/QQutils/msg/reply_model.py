from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ReplyPartKind(str, Enum):
    """一条回复可以包含的消息类型。"""

    TEXT = "text"
    IMAGE = "image"
    RECORD = "record"


@dataclass(frozen=True, slots=True)
class ReplyPart:
    """
    发送前的消息部件。

    此时还不知道 QQ 平台返回的 message_id，因此只描述内容本身。
    """

    kind: ReplyPartKind
    content: str
    file: Path | None = None
    summary: str = ""


@dataclass(frozen=True, slots=True)
class DeliveredPart:
    """已经成功发送并获得平台 message_id 的消息部件。"""

    part: ReplyPart
    message_id: str


@dataclass(frozen=True, slots=True)
class DeliveryFailure:
    """一个消息部件发送失败时的描述信息。"""

    part: ReplyPart
    error: str
    attempted: bool = True


@dataclass(frozen=True, slots=True)
class ReplyDeliveryResult:
    """
    一次回复发送的完整结果。

    即使部分部件失败，也会保留已经成功发送的部件，方便上层补记历史。
    """

    delivered: tuple[DeliveredPart, ...] = ()
    failures: tuple[DeliveryFailure, ...] = ()

    @property
    def sent_any(self) -> bool:
        """是否至少成功发送了一个部件。"""

        return bool(self.delivered)

    @property
    def is_complete(self) -> bool:
        """是否所有部件都发送成功。"""

        return not self.failures


@dataclass(frozen=True, slots=True)
class ReplyOutcome:
    """回复服务对外返回的完整处理结果。"""

    delivery: ReplyDeliveryResult
    recorded_count: int = 0
    record_error: str | None = None
    rate_recorded: bool = False

    @property
    def sent_any(self) -> bool:
        return self.delivery.sent_any

    @property
    def delivered_count(self) -> int:
        return len(self.delivery.delivered)

    @property
    def failed_count(self) -> int:
        return len(self.delivery.failures)

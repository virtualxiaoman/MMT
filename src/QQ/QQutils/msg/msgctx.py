from dataclasses import dataclass
from typing import Union

from ncatbot.core import BotClient, GroupMessage, PrivateMessage, GroupMessageEvent, PrivateMessageEvent

# from src.QQ.QQutils.msg.chat_session import ChatSession
from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper
from src.QQ.QQutils.msg.send_msg import MessageSender
from src.config.QQ_bot_info_loader import BotConfig


@dataclass
class MessageContext:
    bot: BotClient
    msg: Union[GroupMessage, PrivateMessage]
    session: "ChatSession"
    msg_sender: "MessageSender"
    message_wrapper: "RecvMessageWrapper"
    config: "BotConfig"
    tool_text: str
    is_private: bool
    session_id: str

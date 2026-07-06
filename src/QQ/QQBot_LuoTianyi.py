import logging
import time
from typing import Dict

from ncatbot.core import BotClient, GroupMessage, PrivateMessage

from src.QQ.QQutils.cmds.commands import CommandRegistry, ImageCommand, MusicCommand, HelpCommand, \
    CheckinCommand, LyricCommand, DailyReportCommand
from src.QQ.QQutils.msg.chat_session import ChatSession
from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper, SendMessageBuilder
# from src.QQ.QQutils.msg.process_img import MessageNormalizer
from src.QQ.QQutils.msg.send_msg import MessageSender, MessageContext
from src.QQ.QQutils.resource_management.history_storage import HistoryLogger
from src.QQ.QQutils.resource_management.image_storage import ImageStorage
from src.config.QQ_bot_info_loader import BotInfoConfigLoader

# from src.utils.chat.img_describer import ImageDescriber

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
CONFIG = BotInfoConfigLoader.load("LuoTianyi")


class BotManager:
    def __init__(self, bot: BotClient):
        self.bot = bot  # BotClient 实例
        self.sessions: Dict[str, ChatSession] = {}  # 统一存储所有会话，key是 "group_111" 或 "private_111" 以防冲突
        self.msg_sender: MessageSender | None = None  # 当前消息的 sender 对象，后续发送消息都通过它来调用 API
        self.image_storage = ImageStorage(bot_id=CONFIG.qq_id)
        self.history_logger = HistoryLogger(CONFIG)

        # self.image_describer = ImageDescriber()
        # self.message_normalizer = MessageNormalizer(self.image_describer)

        self.registry = CommandRegistry()
        self.registry.register(ImageCommand())
        self.registry.register(MusicCommand(CONFIG.paths.music_dirs))
        self.registry.register(HelpCommand())
        self.registry.register(CheckinCommand())
        self.registry.register(LyricCommand(CONFIG.paths.lyric_dirs))
        self.registry.register(DailyReportCommand())

    def get_session(self, session_id: str, is_private: bool) -> ChatSession:
        prefix = "private_" if is_private else "group_"
        key = f"{prefix}{session_id}"

        if key not in self.sessions:
            self.sessions[key] = ChatSession(session_id, is_private, CONFIG)
        return self.sessions[key]

    async def handle_message(self, msg: PrivateMessage | GroupMessage):
        """
        统一处理群聊和私聊消息
        """
        # user_raw_text = msg.raw_message.strip()
        # print(msg)
        is_private = isinstance(msg, PrivateMessage)
        session_id = str(msg.user_id if is_private else msg.group_id)
        session = self.get_session(session_id, is_private)
        session.session_id = session_id
        logger.info(f"收到消息 type={'private' if is_private else 'group'}, id={session_id}")
        # if not user_raw_text:
        #     return  # 个人觉得空格也不应该被直接丢弃

        # user_raw_text = (
        #     self.message_normalizer
        #     .normalize(msg)
        #     .strip()
        # )
        # print(user_raw_text)

        # =========================
        # 1. 是否能回复（不在黑名单里）
        # =========================
        can_reply = await self._can_reply(session, is_private)
        if not can_reply:
            logger.info(f"黑名单用户/群不回复")
            return

        recv_msg_wrapper = RecvMessageWrapper(msg)
        print(f"原始消息：{recv_msg_wrapper.raw_msg}\nLLM输入消息：{recv_msg_wrapper.text_msg}")
        recv_msg_wrapper = self.image_storage.process(recv_msg_wrapper)  # 保存图片
        self.history_logger.append_recv(msg, recv_msg_wrapper)  # 保存消息（raw+json+LLM输入+人类可读）

        msg_sender = MessageSender(self.bot, msg)
        ctx = MessageContext(
            bot=self.bot,
            msg=msg,
            session=session,
            msg_sender=msg_sender,
            user_raw_text=msg.raw_message.strip(),  # todo： 因为接口变动，工具类暂不使用message_wrapper.text_msg
            is_private=is_private,
            session_id=session_id,
            message_wrapper=recv_msg_wrapper,
            config=CONFIG
        )

        # =========================
        # 2. 工具类指令
        # =========================
        handled = await self.registry.dispatch(ctx)
        if handled:
            return

        # =========================
        # 3. 判断是否回复
        # =========================
        should_reply = await self._should_reply(session, recv_msg_wrapper.text_msg, is_private)
        if not should_reply:
            logger.info(f"决定不回复这条消息")
            return

        # =========================
        # 4. 回复
        # =========================
        ai_reply = await session.get_reply(recv_msg_wrapper.text_msg)  # 生成回复
        emoji_path = session.emoji_decider.get_emoji_path(ai_reply, p=0.5)  # 表情包路径

        text_msg_id = await msg_sender.text(ai_reply)  # 先发送文本回复
        if emoji_path:
            image_msg_id = await msg_sender.image(emoji_path)  # 如果有表情路径，再发送表情
        else:
            image_msg_id = None
        # todo 语音回复

        # =========================
        # 5. 存储回复消息
        # =========================
        builder = SendMessageBuilder(
            recv_msg_wrapper,
            bot_id=str(CONFIG.qq_id),
            bot_name=CONFIG.name_zh,
        )

        send_wrappers = list()
        send_wrappers.append(builder.text(message_id=text_msg_id, text=ai_reply))
        if image_msg_id:
            send_wrappers.append(builder.image(message_id=image_msg_id, file=emoji_path))
        for send_wrapper in send_wrappers:
            self.history_logger.append_send(send_wrapper)  # 保存消息（LLMinput+人类可读）

    async def _can_reply(self, session: ChatSession, is_private: bool) -> bool:
        """
        用assets/config/QQ_reply_settings.yaml判黑/白名单。
        :param session: 对话
        :param is_private: 是否是私聊
        :return:
        """
        return session.qq_reply_settings.can_reply(session.session_id, is_private)

    async def _should_reply(self, session: ChatSession, user_raw_text: str, is_private: bool) -> bool:
        """
        判定是否回复：看回复类型，私聊默认回复，群聊由 decider 判定
        """
        if is_private:
            return True  # 私聊除非被拉黑，不然就默认回复
        return session.reply_decider.check_if_should_reply(user_raw_text)  # 群聊还要由模型判定是否回复


# ========== 运行部分 ==========

bot_client = BotClient()
bot_manager = BotManager(bot_client)  # 创建 BotManager 实例，传入 BotClient


@bot_client.group_event()  # 群聊事件监听
async def on_group_message(msg: GroupMessage):
    await bot_manager.handle_message(msg)


@bot_client.private_event()  # 私聊事件监听
async def on_private_message(msg: PrivateMessage):
    await bot_manager.handle_message(msg)


if __name__ == "__main__":
    bot_client.run(bt_uin=CONFIG.qq_id)

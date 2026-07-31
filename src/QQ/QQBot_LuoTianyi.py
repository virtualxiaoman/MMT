import logging
import os
import random
import time
from pathlib import Path
from typing import Dict

# ncatbot 内部大量使用相对路径(Path.cwd())读取配置，
# 因此必须先切换工作目录，再导入 ncatbot。
QQ_ROOT = Path(__file__).resolve().parent
os.chdir(QQ_ROOT)
# print(f"cwd = {os.getcwd()}")
# print(f"__file__ = {Path(__file__).resolve()}")

from ncatbot.core import BotClient, GroupMessage, PrivateMessage

from src.QQ.QQutils.cmds.commands import CommandRegistry, ImageCommand, MusicCommand, HelpCommand, \
    CheckinCommand, LyricCommand, DailyReportCommand, BanCommand, MorningCommand, ImageGeneratorCommand, \
    UpdateMemoryCommand
from src.QQ.QQutils.msg.chat_session import ChatSession, MessageContext
from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper, SendMessageBuilder
# from src.QQ.QQutils.msg.process_img import MessageNormalizer
from src.QQ.QQutils.msg.send_msg import MessageSender
from src.QQ.QQutils.res.history_loader import HistoryLoader
from src.QQ.QQutils.res.history_storage import HistoryLogger
from src.QQ.QQutils.res.image_storage import ImageStorage
from src.config.QQ_bot_info_loader import BotInfoConfigLoader
from src.utils.chat.decider.reply_decider import ReplyDecisionData

# from src.utils.chat.img_describer import ImageDescriber

# api：https://docs.ncatbot.xyz/reference
# prompt：https://chatgpt.com/c/6a4cfe69-eb3c-83ec-b319-c00f95d8e146

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
CONFIG = BotInfoConfigLoader.load("LuoTianyi")


class BotManager:
    def __init__(self, bot: BotClient):
        self.bot = bot  # BotClient 实例
        self.sessions: Dict[str, ChatSession] = {}  # 统一存储所有会话，key是 "group_111" 或 "private_111" 以防冲突
        # self.msg_sender: MessageSender | None = None  # 当前消息的 sender 对象，后续发送消息都通过它来调用 API
        self.image_storage = ImageStorage(bot_id=CONFIG.bot_id)
        # self.history_logger = HistoryLogger(CONFIG)

        # self.image_describer = ImageDescriber()
        # self.message_normalizer = MessageNormalizer(self.image_describer)

        self.registry = CommandRegistry()
        self._init_registry()

    def get_session(self, session_id: str, is_private: bool) -> ChatSession:
        prefix = "private_" if is_private else "group_"
        key = f"{prefix}{session_id}"
        if key not in self.sessions:
            self.sessions[key] = ChatSession(session_id, is_private, CONFIG)
        return self.sessions[key]

    # api参考 https://docs.ncatbot.xyz/reference
    async def handle_message(self, msg: PrivateMessage | GroupMessage):
        """
        统一处理群聊和私聊消息
        """
        # for _ in range(12):
        #     await self.bot.api.send_poke(
        #         group_id="1039857271", user_id="2705227496"
        #     )
        # await self.bot.api.set_msg_emoji_like(
        #     message_id="1311274050", emoji_id="424", set=True
        # )

        is_private = isinstance(msg, PrivateMessage)
        session_id = str(msg.user_id if is_private else msg.group_id)
        session = self.get_session(session_id, is_private)
        session.session_id = session_id
        logger.info(f"收到消息 type={'private' if is_private else 'group'}, id={session_id}")

        # =========================
        # 1. 是否能回复（不在黑名单里）
        # =========================
        can_reply = await self._can_reply(session, is_private)
        if not can_reply:
            logger.info(f"黑名单用户/群不回复")
            return

        # =========================
        # 2. 格式化消息，处理多模态数据，建立ctx
        # =========================
        recv_msg_wrapper = RecvMessageWrapper(msg)
        recv_msg_wrapper.process_content()
        print(f"原始消息：{recv_msg_wrapper.raw_msg}\nLLM输入消息：{recv_msg_wrapper.llm_msg}\n"
              f"工具类输入消息：{recv_msg_wrapper.tool_msg}")
        recv_msg_wrapper = self.image_storage.process(recv_msg_wrapper)  # 保存图片

        history_logger = HistoryLogger(config=CONFIG)
        history_logger.append_recv(msg, recv_msg_wrapper)  # 保存消息（raw+json+LLM输入+人类可读）

        msg_sender = MessageSender(self.bot, session_id=session_id, is_private=is_private)
        ctx = MessageContext(
            bot=self.bot,
            msg=msg,
            session=session,
            msg_sender=msg_sender,
            tool_text=recv_msg_wrapper.tool_msg,
            is_private=is_private,
            session_id=session_id,
            recv_msg_wrapper=recv_msg_wrapper,
            config=CONFIG
        )
        if not ctx.session.rate_limiter.allow():
            logger.info(f"{ctx.session.session_id} 回复过于频繁，跳过")
            return
        # =========================
        # 3. 工具类指令
        # =========================
        handled = await self.registry.dispatch(ctx)
        if handled:
            ctx.session.rate_limiter.record()  # 记录
            return

        # =========================
        # 调用计时器+计数器回复消息的逻辑
        # =========================
        await session.reply_scheduler.on_new_message(ctx)

    def _init_registry(self):
        self.registry.register(ImageCommand())
        self.registry.register(MusicCommand(CONFIG.paths.music_dirs))
        self.registry.register(HelpCommand())
        self.registry.register(CheckinCommand())
        self.registry.register(LyricCommand(CONFIG.paths.lyric_dirs))
        self.registry.register(DailyReportCommand())
        self.registry.register(BanCommand())
        self.registry.register(MorningCommand())
        self.registry.register(ImageGeneratorCommand(CONFIG))
        self.registry.register(UpdateMemoryCommand())

    async def _can_reply(self, session: ChatSession, is_private: bool) -> bool:
        """
        用assets/config/QQ_reply_settings.yaml判黑/白名单。
        :param session: 对话
        :param is_private: 是否是私聊
        :return:
        """
        return session.qq_reply_settings.can_reply(session.session_id, is_private)


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
    bot_client.run(bt_uin=CONFIG.bot_id)

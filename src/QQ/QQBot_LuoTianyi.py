import logging
import time
from typing import Dict

from ncatbot.core import BotClient, GroupMessage, PrivateMessage

from src.QQ.QQutils.cmds.commands import CommandRegistry, ImageCommand, MusicCommand, HelpCommand, \
    CheckinCommand, LyricCommand
from src.QQ.QQutils.msg.chat_session import ChatSession
from src.QQ.QQutils.msg.msg_wrapper import MessageWrapper
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


# # 配置
# BOT_NAME = "天依"
# BOT_QQ_ID = 1121221045
# RAND_PIC_PATHS = [
#     "F:/Picture/pixiv/LuoTianyi"
# ]
# MUSIC_DIR = "F:/Audio/Music"


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

        message_wrapper = MessageWrapper(msg)
        print(f"原始消息：{message_wrapper.raw_msg}\nLLM输入消息：{message_wrapper.text_msg}")
        message_wrapper = self.image_storage.process(message_wrapper)  # 保存图片
        self.history_logger.append(msg, message_wrapper)  # 保存消息（raw+json+LLM输入+人类可读）

        msg_sender = MessageSender(self.bot, msg)
        ctx = MessageContext(
            bot=self.bot,
            msg=msg,
            session=session,
            msg_sender=msg_sender,
            user_raw_text=msg.raw_message.strip(),  # todo： 因为接口变动，工具类暂不使用message_wrapper.text_msg
            is_private=is_private,
            session_id=session_id
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
        should_reply = await self._should_reply(session, message_wrapper.text_msg, is_private)
        if not should_reply:
            logger.info(f"决定不回复这条消息")
            return

        # =========================
        # 4. 回复
        # =========================
        ai_reply = await session.get_reply(message_wrapper.text_msg)  # 生成回复
        emoji_path = session.emoji_decider.get_emoji_path(ai_reply, p=0.4)  # 表情包路径

        await msg_sender.text(ai_reply)  # 先发送文本回复
        if emoji_path:
            await msg_sender.image(emoji_path)  # 如果有表情路径，再发送表情

    # todo 语音回复

    # async def handle_message(self, msg: Union[GroupMessage, PrivateMessage]):
    #     """
    #     统一处理群聊和私聊消息
    #     """
    #     user_text = msg.raw_message.strip()
    #     is_private = isinstance(msg, PrivateMessage)
    #     session_id = str(msg.user_id if is_private else msg.group_id)  # 获取唯一标识 ID
    #     logger.info(
    #         f"收到消息 type={'private' if is_private else 'group'} "
    #         f"id={session_id} text={user_text}"
    #     )
    #     session = self.get_session(session_id, is_private)  # 获取或创建会话
    #     session.session_id = session_id  # 确保会话 ID 是最新的
    #     self.msg_sender = MessageSender(self.bot, msg)  # 统一 sender 对象，后续发送消息都通过它来调用 API
    #
    #     if not user_text:
    #         return
    #
    #     # --- 1. 优先判定工具类指令 ---
    #     # 直接调用新抽离的方法，如果处理了就 return
    #     if await self._handle_commands(msg, session):
    #         return
    #
    #     # --- 2. 使用统一的判断函数 ---
    #     should_reply = await self.__should_reply(session, user_text, is_private)
    #
    #     if not should_reply:
    #         logger.info(f"决定不回复这条消息: {user_text}")
    #         return
    #
    #     ai_reply = await session.get_reply(user_text)  # 生成回复
    #     emoji_path = session.emoji_decider.get_emoji_path(ai_reply, p=0.4)  # 表情包路径
    #
    #     await self.msg_sender.text(ai_reply)  # 先发送文本回复
    #     if emoji_path:
    #         await self.msg_sender.image(emoji_path)  # 如果有表情路径，再发送表情
    #
    #   async def _handle_commands(self, msg: Union[GroupMessage, PrivateMessage], session) -> bool:
    #       """
    #       处理特定指令（如：一图）
    #       返回 True 表示指令已匹配并处理，主程序应直接 return
    #       """
    #       user_text = msg.raw_message.strip()
    #
    #       # --- 指令1：一图 ---可以以一图开始，比如指令“一图 -n 5”表示发5张图，默认发1张
    #       if user_text == "一图" or user_text.startswith("一图 "):
    #           # 解析指令参数，目前仅支持“-n 数字”来指定图片数量，默认1张
    #           pic_nums = 1  # default
    #           if user_text.startswith("一图 "):
    #               parts = user_text.split()
    #               if len(parts) >= 3 and parts[1] == "-n" and parts[2].isdigit():
    #                   pic_nums = max(1, min(int(parts[2]), 3))
    #               else:
    #                   pic_nums = 1  # 如果参数不正确，默认发1张图
    #
    #           for i in range(pic_nums):
    #               random_path = session.random_picture_provider.get_random_image_path()
    #               if i == 0:
    #                   await self.msg_sender.text(f"呐呐呐~coins-{5 * pic_nums}")  # 首次发文本提示扣除金币，后续只发图
    #               await self.msg_sender.image(random_path)  # 发送图片
    #
    #           return True
    #
    #       # --- 指令2：唱歌 ---
    #       if user_text.startswith("唱") and len(user_text) > 1:
    #           song_name = user_text[1:].strip()
    #           record_path = await self.__find_music_file(song_name)
    #           logger.info(f"歌曲名: '{song_name}'，音乐文件路径是: {record_path}")
    #           if record_path:
    #               await self.msg_sender.record(record_path)
    #           else:
    #               await self.msg_sender.text(f"抱歉，天依还不会唱{song_name}这首歌呢~你可以教教天依吗(>_<)")
    #               logger.warning(f"未找到匹配的音乐文件，无法满足用户的唱歌请求: '{song_name}'")
    #           return True
    #
    #       # --- 指令3：帮助 ---
    #       if user_text.lower() in ["help", "帮助", "菜单", "功能"]:
    #           help_text = """꧁ 华风夏韵，洛水天依 ꧂
    # ♾️ 这里是天依，请多指教(,,>᎑<,,)
    # 🎨 图片小惊喜：
    #   -> 发送「一图」 → 天依会送你一张可爱的图片哦~ 如果想看更多，试试「一图 -n 2」，可以一次看到两张呢~
    # 🎤 为了你唱下去：
    #   -> 发送「唱+歌名」 → 天依来为你唱这首歌（比如：唱为了你唱下去）
    # 📋 小说明：
    #   -> 私聊的话，天依一定会好好地回应你哟(♡>𖥦<)/♡ 群聊里除了这些特别的指令，天依还在努力学习，希望能更好地陪着你(◔◡◔)
    #   -> 如果遇到什么问题，可以找我的好朋友virtual小满，她会帮你哒(⑅˃◡˂⑅)
    # ❤️ （轻轻歪头，眼里闪着温暖的光）诶嘿~天依虽然是纸片人，但通过歌声和大家的爱，真的能变得更有温度呢！天依会一直一直在这里，陪着你，唱歌给大家听的(๑>؂<๑）"""
    #           await self.msg_sender.text(help_text)
    #           return True
    #
    #       # --- 指令4：群打卡/签到 ---
    #       if user_text == "打卡":
    #           try:
    #               await self.bot.api.set_group_sign(
    #                   group_id=msg.group_id
    #               )
    #
    #               await self.bot.api.post_group_msg(
    #                   group_id=msg.group_id,
    #                   text="群签到完成~"
    #               )
    #               logger.info(f"已完成群 {msg.group_id} 的签到")
    #           except Exception as e:
    #               logger.error(f"群签到失败: {e}")
    #               await self.bot.api.post_group_msg(
    #                   group_id=msg.group_id,
    #                   text=f"签到失败了呢...{e}"
    #               )
    #           return True
    #
    #       return False

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

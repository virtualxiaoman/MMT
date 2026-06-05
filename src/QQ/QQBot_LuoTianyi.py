import asyncio
import logging
from pathlib import Path
from typing import Dict, Union

from ncatbot.core import BotClient, GroupMessage, PrivateMessage  # 导入 PrivateMessage

from src.config.QQ_reply_settings import QQReplySettings
from src.config.path import VOICE_DIR
from src.config.cur_role import current_role
from src.utils.chat.role_chat import ChatDSAPI
from src.utils.chat.reply_decider import ReplyDecider
from src.utils.chat.emoji_decider import EmojiDecider
from src.utils.chat.voice_decider import VoiceDecider
from src.utils.tools.rand_pic import RandomPicture

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
BOT_NAME = "天依"
BOT_QQ_ID = 1121221045
RAND_PIC_PATHS = [
    "F:/Picture/pixiv/LuoTianyi"
]
MUSIC_DIR = "F:/Audio/Music"


class ChatSession:
    def __init__(self, session_id: str, is_private: bool = False):
        self.session_id = session_id
        self.is_private = is_private
        self.ai_backend = ChatDSAPI()  # 默认deepseek
        self.reply_decider = ReplyDecider(name=BOT_NAME, qq_id=BOT_QQ_ID)
        self.emoji_decider = EmojiDecider()
        self.ai_backend.init_role(BOT_NAME)
        self.random_picture = RandomPicture(RAND_PIC_PATHS)
        self.qq_reply_settings = QQReplySettings(BOT_QQ_ID)
        logger.info(f"已为{'私聊' if is_private else '群聊'} {session_id} 初始化 AI 会话")

    async def get_reply(self, text: str) -> str:
        """调用 AI 生成回复"""
        try:
            # ChatDSAPI.one_chat 是同步的
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.ai_backend.one_chat, text)
        except Exception as e:
            logger.error(f"AI 生成回复失败: {e}")
            return "呜... 脑子转不过来了..."


class MessageSender:
    def __init__(self, bot: BotClient, msg: Union[GroupMessage, PrivateMessage]):
        self.bot = bot
        self.msg = msg
        self.is_private = isinstance(msg, PrivateMessage)

    # 文本
    async def text(self, content: str):
        if self.is_private:
            await self.bot.api.post_private_msg(
                user_id=self.msg.user_id,
                text=content
            )
        else:
            await self.bot.api.post_group_msg(
                group_id=self.msg.group_id,
                text=content
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id} 的文本消息: {content}")

    # 图片
    async def image(self, path: str):
        if self.is_private:
            await self.bot.api.post_private_msg(
                user_id=self.msg.user_id,
                image=path
            )
        else:
            await self.bot.api.post_group_msg(
                group_id=self.msg.group_id,
                image=path
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id}，图片路径为: {path}")

    # 语音
    async def record(self, path: str):
        if self.is_private:
            await self.bot.api.send_private_record(
                user_id=self.msg.user_id,
                file=path
            )
        else:
            await self.bot.api.send_group_record(
                group_id=self.msg.group_id,
                file=path
            )
        logger.info(f"已回复{'用户' if self.is_private else '群'} "
                    f"{self.msg.user_id if self.is_private else self.msg.group_id}，语音路径为: {path}")


class BotManager:
    def __init__(self, bot: BotClient):
        self.bot = bot  # BotClient 实例
        self.sessions: Dict[str, ChatSession] = {}  # 统一存储所有会话，key是 "group_111" 或 "private_111" 以防冲突
        self.sender: MessageSender | None = None  # 当前消息的 sender 对象，后续发送消息都通过它来调用 API

    def get_session(self, session_id: str, is_private: bool) -> ChatSession:
        prefix = "private_" if is_private else "group_"
        key = f"{prefix}{session_id}"

        if key not in self.sessions:
            self.sessions[key] = ChatSession(session_id, is_private)
        return self.sessions[key]

    async def handle_message(self, msg: Union[GroupMessage, PrivateMessage]):
        """
        统一处理群聊和私聊消息
        """
        user_text = msg.raw_message.strip()
        is_private = isinstance(msg, PrivateMessage)
        session_id = str(msg.user_id if is_private else msg.group_id)  # 获取唯一标识 ID
        logger.info(f"收到{'私聊' if is_private else '群【' + session_id + '】'}消息: {user_text}")
        session = self.get_session(session_id, is_private)  # 获取或创建会话
        session.session_id = session_id  # 确保会话 ID 是最新的
        self.sender = MessageSender(self.bot, msg)  # 统一 sender 对象，后续发送消息都通过它来调用 API

        if not user_text:
            return

        # --- 1. 优先判定工具类指令 ---
        # 直接调用新抽离的方法，如果处理了就 return
        if await self._handle_commands(msg, session):
            return

        # --- 2. 使用统一的判断函数 ---
        should_reply = await self.__should_reply(session, user_text, is_private)

        if not should_reply:
            logger.info(f"决定不回复这条消息: {user_text}")
            return

        ai_reply = await session.get_reply(user_text)  # 生成回复
        emoji_path = session.emoji_decider.get_emoji_path(ai_reply, p=0.4)  # 表情包路径
        # voice_decider = VoiceDecider(Path(VOICE_DIR) / f"{current_role.name_en}/description.csv")  # 初始化匹配器
        # voice_path = voice_decider.match(ai_reply, threshold=0.712)
        # if voice_path:
        #     voice_path = str(Path(VOICE_DIR) / f"{current_role.name_en} / voice_path")  # 获取语音路径
        # # 根据消息类型调用不同 API
        # if is_private:
        #     await self.bot.api.post_private_msg(user_id=msg.user_id, text=ai_reply)
        #     if emoji_path:
        #         await self.bot.api.post_private_msg(user_id=msg.user_id, image=emoji_path)
        #     # if voice_path:
        #     #     await bot.api.send_private_record(user_id=msg.user_id, file=voice_path)
        #     # record_path = "G:/Projects/py/MMT/assets/voice/Shiroko/0076.wav"
        #     # record_path = "F:/Audio/Music/流光协奏演唱会版《为了你唱下去》编曲扒带(BV1xNsLzaEQ7).mp3"
        #     # await bot.api.send_private_record(user_id=msg.user_id, file=record_path)
        #     logger.info(f"已回复用户 {msg.user_id} 的私聊消息")
        # else:
        #     await self.bot.api.post_group_msg(group_id=msg.group_id, text=ai_reply)
        #     if emoji_path:
        #         await self.bot.api.post_group_msg(group_id=msg.group_id, image=emoji_path)
        #     # if voice_path:
        #     #     await bot.api.send_group_record(group_id=msg.group_id, file=voice_path)
        #     # record_path = "F:/Audio/Music/洛天依 - 为了你唱下去_EM.flac"
        #     # await bot.api.send_group_record(group_id=msg.group_id, file=record_path)
        #     logger.info(f"已回复群 {msg.group_id} 的消息")
        await self.sender.text(ai_reply)  # 先发送文本回复
        if emoji_path:
            await self.sender.image(emoji_path)  # 如果有表情路径，再发送表情
        # todo 语音回复

    async def _handle_commands(self, msg: Union[GroupMessage, PrivateMessage], session) -> bool:
        """
        处理特定指令（如：一图）
        返回 True 表示指令已匹配并处理，主程序应直接 return
        """
        user_text = msg.raw_message.strip()
        is_private = isinstance(msg, PrivateMessage)

        # --- 指令1：一图 ---可以以一图开始，比如指令“一图 -n 5”表示发5张图，默认发1张
        if user_text == "一图" or user_text.startswith("一图 "):
            # 解析指令参数，目前仅支持“-n 数字”来指定图片数量，默认1张
            pic_nums = 1  # default
            if user_text.startswith("一图 "):
                parts = user_text.split()
                if len(parts) >= 3 and parts[1] == "-n" and parts[2].isdigit():
                    pic_nums = max(1, min(int(parts[2]), 3))
                else:
                    pic_nums = 1  # 如果参数不正确，默认发1张图

            for i in range(pic_nums):
                random_path = session.random_picture.get_random_image_path()
                if i == 0:
                    await self.sender.text(f"呐呐呐~coins-{5 * pic_nums}")  # 首次发文本提示扣除金币，后续只发图
                    # todo 实际扣除金币逻辑
                await self.sender.image(random_path)  # 发送图片

            #     if is_private:
            #         if i == 0:  # 只有第一张图前面发 coins-5 的文本，后续图片只发图
            #             await self.bot.api.post_private_msg(user_id=msg.user_id, text=f"呐呐呐~coins-{5 * pic_nums}")
            #         await self.bot.api.post_private_msg(user_id=msg.user_id, image=random_path)
            #     else:
            #         if i == 0:  # 只有第一张图前面发 coins-5 的文本，后续图片只发图
            #             await self.bot.api.post_group_msg(group_id=msg.group_id, text=f"呐呐呐~coins-{5 * pic_nums}")
            #         await self.bot.api.post_group_msg(group_id=msg.group_id, image=random_path)
            #
            #     target_id = msg.user_id if is_private else msg.group_id
            # logger.info(f"已回复{'用户' if is_private else '群'} {target_id} 的随机图片: {random_path}")
            return True

        # --- 指令2：唱歌 ---
        if user_text.startswith("唱") and len(user_text) > 1:
            song_name = user_text[1:].strip()
            record_path = await self.__find_music_file(song_name)
            print(f"歌曲名: '{song_name}'，音乐文件路径是: {record_path}")
            if record_path:
                await self.sender.record(record_path)
                # if is_private:
                #     await self.bot.api.send_private_record(user_id=msg.user_id, file=record_path)
                # else:
                #     await self.bot.api.send_group_record(group_id=msg.group_id, file=record_path)
            else:
                await self.sender.text(f"抱歉，天依还不会唱{song_name}这首歌呢~你可以教教天依吗(>_<)")
                logger.warning(f"未找到匹配的音乐文件，无法满足用户的唱歌请求: '{song_name}'")
            return True

        # --- 指令3：帮助 ---
        if user_text.lower() in ["help", "帮助", "菜单", "功能"]:
            help_text = """꧁ 华风夏韵，洛水天依 ꧂
  ♾️ 这里是天依，请多指教(,,>᎑<,,)
  🎨 图片小惊喜：
    -> 发送「一图」 → 天依会送你一张可爱的图片哦~ 如果想看更多，试试「一图 -n 2」，可以一次看到两张呢~
  🎤 为了你唱下去：
    -> 发送「唱+歌名」 → 天依来为你唱这首歌（比如：唱为了你唱下去）
  📋 小说明：
    -> 私聊的话，天依一定会好好地回应你哟(♡>𖥦<)/♡ 群聊里除了这些特别的指令，天依还在努力学习，希望能更好地陪着你(◔◡◔)
    -> 如果遇到什么问题，可以找我的好朋友virtual小满，她会帮你哒(⑅˃◡˂⑅)
  ❤️ （轻轻歪头，眼里闪着温暖的光）诶嘿~天依虽然是纸片人，但通过歌声和大家的爱，真的能变得更有温度呢！天依会一直一直在这里，陪着你，唱歌给大家听的(๑>؂<๑）"""
            await self.sender.text(help_text)
            return True

        # --- 指令4：群打卡/签到 ---todo 应该只支持群聊，私聊不处理
        if user_text == "打卡":
            try:
                await bot_client.api.set_group_sign(
                    group_id=msg.group_id
                )

                await bot_client.api.post_group_msg(
                    group_id=msg.group_id,
                    text="群签到完成~"
                )
                logger.info(f"已完成群 {msg.group_id} 的签到")
            except Exception as e:
                logger.error(f"群签到失败: {e}")
                await bot_client.api.post_group_msg(
                    group_id=msg.group_id,
                    text=f"签到失败了呢...{e}"
                )
            return True

        return False

    async def __should_reply(self, session: ChatSession, user_text: str, is_private: bool) -> bool:
        """
        判定是否回复：
          1. 先用assets/config/QQ_reply_settings.yaml判黑/白名单。
          2. 再看回复类型，私聊默认回复，群聊由 decider 判定
        """
        can_reply = session.qq_reply_settings.can_reply(session.session_id, is_private)
        if not can_reply:
            return False  # 黑名单用户/群不回复
        if is_private:
            return True  # 私聊除非被拉黑，不然就默认回复
        return session.reply_decider.check_if_should_reply(user_text)  # 群聊还要由模型判定是否回复

    async def __find_music_file(self, song_name: str) -> str | None:
        """
        在指定目录下搜索包含 song_name 的音频文件
        """
        extensions = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac'}  # 支持的音频文件扩展名
        music_dir = Path(MUSIC_DIR)

        # 如果目录不存在，直接返回 None
        if not music_dir.exists():
            logger.error(f"音乐目录不存在: {music_dir}")
            return None

        # 遍历目录下所有文件
        for file in music_dir.rglob("*"):
            # file.is_file() 确保它是文件而不是文件夹
            # song_name.lower() in file.name.lower() 实现不区分大小写的包含匹配
            if file.is_file() and file.suffix.lower() in extensions:
                if song_name.lower() in file.name.lower():
                    # print(f"找到匹配的音乐文件: '{file.name}'，路径: {file.absolute()}")
                    return str(file.absolute())  # 返回绝对路径的字符串形式

        return None


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
    bot_client.run(bt_uin=BOT_QQ_ID)

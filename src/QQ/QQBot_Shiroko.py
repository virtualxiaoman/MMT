import asyncio
import logging
from typing import Dict, Union

from ncatbot.core import BotClient, GroupMessage, PrivateMessage  # 导入 PrivateMessage
from src.utils.chat import ChatDSAPI
from src.utils.reply_decider import ReplyDecider
from src.utils.emoji_decider import EmojiDecider

# todo 戳一戳 https://github.com/liyihao1110/ncatbot/issues/231

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 配置
BOT_NAME = "白子"
BOT_QQ_ID = 1291606697


class ChatSession:
    def __init__(self, session_id: str, is_private: bool = False):
        self.session_id = session_id
        self.is_private = is_private
        self.ai_backend = ChatDSAPI()  # 默认deepseek
        self.reply_decider = ReplyDecider(name=BOT_NAME, qq_id=BOT_QQ_ID)
        self.emoji_decider = EmojiDecider()
        self.ai_backend.init_role(BOT_NAME)
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


class BotManager:
    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}  # 统一存储所有会话，key是 "group_111" 或 "private_111" 以防冲突

    def get_session(self, session_id: str, is_private: bool) -> ChatSession:
        prefix = "private_" if is_private else "group_"
        key = f"{prefix}{session_id}"

        if key not in self.sessions:
            self.sessions[key] = ChatSession(session_id, is_private)
        return self.sessions[key]

    async def handle_message(self, bot: BotClient, msg: Union[GroupMessage, PrivateMessage]):
        """
        统一处理群聊和私聊消息
        """
        user_text = msg.raw_message.strip()
        is_private = isinstance(msg, PrivateMessage)
        session_id = str(msg.user_id if is_private else msg.group_id)  # 获取唯一标识 ID
        logger.info(f"收到{'私聊' if is_private else '群【' + session_id + '】'}消息: {user_text}")

        if not user_text:
            return

        session = self.get_session(session_id, is_private)

        # 判定是否回复：私聊默认回复，群聊由 decider 判定
        should_reply = True if is_private else session.reply_decider.check_if_should_reply(user_text)
        if should_reply:
            ai_reply = await session.get_reply(user_text)  # 生成回复
            emoji_path = session.emoji_decider.get_emoji_path(ai_reply, p=1)  # 表情包路径
            # image_cq = f"[CQ:image,file=file:///{emoji_path}]"
            # final_reply = f"{ai_reply}\n{image_cq}"  # 合并文本和图片
            # 根据消息类型调用不同 API
            if is_private:
                await bot.api.post_private_msg(user_id=msg.user_id, text=ai_reply)
                if emoji_path:
                    await bot.api.post_private_msg(user_id=msg.user_id, image=emoji_path)
                logger.info(f"已回复用户 {msg.user_id} 的私聊消息")
            else:
                await bot.api.post_group_msg(group_id=msg.group_id, text=ai_reply)
                if emoji_path:
                    await bot.api.post_group_msg(group_id=msg.group_id, image=emoji_path)
                logger.info(f"已回复群 {msg.group_id} 的消息")

        else:
            logger.info(f"决定不回复这条消息: {user_text}")


# ========== 运行部分 ==========

bot_client = BotClient()
bot_manager = BotManager()


@bot_client.group_event()  # 群聊事件监听
async def on_group_message(msg: GroupMessage):
    await bot_manager.handle_message(bot_client, msg)


@bot_client.private_event()  # 私聊事件监听
async def on_private_message(msg: PrivateMessage):
    await bot_manager.handle_message(bot_client, msg)


if __name__ == "__main__":
    bot_client.run()

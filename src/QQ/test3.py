import asyncio
import logging
from typing import Dict

from ncatbot.core import BotClient, GroupMessage
# 假设这些是你自己的工具类
from src.utils.chat import ChatDSAPI
from src.utils.decider import ReplyDecider

# ========== 配置区域 ==========
BOT_NAME = "白子"
BOT_QQ_ID = 1291606697

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ========== 核心逻辑封装 ==========

class ChatSession:
    """
    单个会话的管理类，封装了 AI 记忆和回复决策逻辑
    """

    def __init__(self, group_id: str):
        self.group_id = group_id
        self.ai_backend = ChatDSAPI()
        self.decider = ReplyDecider(name=BOT_NAME, qq_id=BOT_QQ_ID)

        # 初始化角色设定
        self.ai_backend.init_role(BOT_NAME)
        logger.info(f"已为群 {group_id} 初始化专属 AI 会话")

    async def get_response(self, text: str) -> str:
        """调用 AI 生成回复"""
        try:
            # ChatDSAPI.one_chat 是同步的
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.ai_backend.one_chat, text)
        except Exception as e:
            logger.error(f"AI 生成回复失败: {e}")
            return "呜... 脑子转不过来了..."


class BotManager:
    """
    机器人逻辑管理器
    """

    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}

    def get_group_session(self, group_id: str) -> ChatSession:
        if group_id not in self.sessions:
            self.sessions[group_id] = ChatSession(group_id)
        return self.sessions[group_id]

    async def handle_message(self, bot: BotClient, msg: GroupMessage):
        user_text = msg.raw_message.strip()
        print(f"收到群【{msg.group_id}】中用户【{msg.user_id}】的消息: {user_text}")
        if not user_text:
            return
        session = self.get_group_session(msg.group_id)
        if session.decider.check_if_should_reply(user_text):
            logger.info(f"群【{msg.group_id}】命中触发条件: {user_text}")  # 1. 决策是否回复
            ai_reply = await session.get_response(user_text)  # 2. 获取 AI 回复
            await bot.api.post_group_msg(group_id=msg.group_id, text=ai_reply)  # 3. 发送消息
        else:
            logger.debug(f"群【{msg.group_id}】消息未触发回复")


# ========== 运行部分 ==========

bot = BotClient()
manager = BotManager()


@bot.group_event()
async def on_group_message(msg: GroupMessage):
    await manager.handle_message(bot, msg)


if __name__ == "__main__":
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("机器人已停止")

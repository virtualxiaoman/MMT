import asyncio
import logging

from src.config.QQ_bot_info_loader import BotConfig
from src.config.QQ_reply_settings import QQReplySettings
from src.utils.chat.decider.emoji_decider import EmojiDecider
from src.utils.chat.decider.reply_decider import ReplyDecider
from src.utils.chat.role_chat import ChatDSAPI
from src.utils.tools.resource_management.rand_pic import RandomPicture

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ChatSession:
    def __init__(self, session_id: str, is_private: bool = False, config: BotConfig | None = None):
        self.session_id = session_id
        self.is_private = is_private
        self.llm_chater = ChatDSAPI()  # 默认deepseek
        self.reply_decider = ReplyDecider(config)
        self.emoji_decider = EmojiDecider()
        self.llm_chater.init_role(config.name_zh)
        self.random_picture_provider = RandomPicture(config.paths.random_picture_dirs)
        self.qq_reply_settings = QQReplySettings(config.qq_id)
        logger.info(f"已为{'私聊' if is_private else '群聊'} {session_id} 初始化 AI 会话")

    async def get_reply(self, text: str) -> str:
        """调用 AI 生成回复"""
        try:
            # ChatDSAPI.one_chat 是同步的
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.llm_chater.one_chat, text)
        except Exception as e:
            logger.error(f"AI 生成回复失败: {e}")
            return "呜... 脑子转不过来了..."

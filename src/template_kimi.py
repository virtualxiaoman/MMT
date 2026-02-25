# https://platform.moonshot.cn
# https://platform.moonshot.cn/docs/api/partial#%E8%A7%92%E8%89%B2%E6%89%AE%E6%BC%94

from src.utils.chat import ChatKimiAPI

role_name = "砂狼白子"
chat_kimi = ChatKimiAPI()
chat_kimi.init_role(role_name)
chat_kimi.multi_chat()

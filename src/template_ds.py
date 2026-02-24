# https://platform.deepseek.com/usage

from src.utils import ChatDSAPI

role_name = "砂狼白子"
chat_ds = ChatDSAPI()
chat_ds.init_role(role_name)
chat_ds.multi_chat()

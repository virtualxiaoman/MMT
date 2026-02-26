from src.utils.chat import ChatDSAPI

role_name = "砂狼白子"
chat_ds = ChatDSAPI()
chat_ds.init_role(role_name)
chat_ds.multi_chat()
# from src.utils import ChatKimiAPI
#
# role_name = "砂狼白子"
# chat_kimi = ChatKimiAPI()
# chat_kimi.init_role(role_name)
# chat_kimi.multi_chat()

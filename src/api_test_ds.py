# Please install OpenAI SDK first: `pip3 install openai`

from openai import OpenAI
from src.utils import load_from_txt, ChatDS

role_name = "阿洛娜"
chat_ds = ChatDS()
chat_ds.init_role(role_name)
# queries = ["你好，你是谁？详细告诉我一下你的情况吧？",
#            "我跟你是什么关系呀？"]
# chat_ds.multi_chat(queries)
chat_ds.multi_chat()

# client = OpenAI(
#     api_key=load_from_txt("../resources/api_key/deepseek.txt"),
#     base_url="https://api.deepseek.com"
# )
#
# role_name = "阿洛娜"
# msg = [
#     init_role_prompt(role_name),  # 角色设定提示
# ]
#
#
# def chat(query, msg):
#     msg.append({
#         "role": "user",
#         "content": query
#     })
#     # print(msg)
#     try:
#         completion = client.chat.completions.create(
#             model="deepseek-chat",
#             messages=msg,
#             temperature=1.3,  # deepseek建议通用对话设置为1.3：https://api-docs.deepseek.com/zh-cn/quick_start/parameter_settings
#             stream=False
#         )
#         result = completion.choices[0].message.content
#
#     except Exception as e:
#         print("发生错误，具体如下：")
#         print(f"消息：{msg}")
#         print(f"错误：{e}")
#         return "对话异常，请检查错误码"
#
#     # 如果对话正常，将对话记录添加到msg中
#     msg.append({
#         "role": "assistant",
#         "content": result
#     })
#     return result
#
#
# while True:
#     user_input = input(">>> ")
#     if user_input.strip().lower() == "quit":
#         print(f"与{role_name}的对话结束")
#         break
#     ans = chat(user_input, msg)
#     print(ans)
#     # print("--------------------------------------")
#
# # print(chat("你好，你是谁？详细告诉我一下你的情况吧？", msg))
# # print("--------------------------------------")
# # print(chat("我跟你是什么关系呀？", msg))
#
# print("over")
# # response = client.chat.completions.create(
# #     model="deepseek-chat",
# #     messages=[
# #         {"role": "system", "content": "You are a helpful assistant"},
# #         {"role": "user", "content": "Hello"},
# #     ],
# #     stream=False
# # )
# #
# # print(response.choices[0].message.content)

# https://platform.moonshot.cn
# https://platform.moonshot.cn/docs/api/partial#%E8%A7%92%E8%89%B2%E6%89%AE%E6%BC%94
from openai import OpenAI
from src.utils import load_from_txt

client = OpenAI(
    api_key=load_from_txt("../resources/api_key/kimi.txt"),
    base_url="https://api.moonshot.cn/v1",
)

# 定义砂狼白子的角色设定提示词
role_prompt = load_from_txt("../resources/prompt/Shiroko.txt")
# role_prompt = load_from_txt("../resources/prompt/Arona.txt")

role_name = "砂狼白子"

role_system = {
    "role": "system",
    "content": role_prompt,
}

# # 通过预填（Prefill）部分模型回复来引导模型的输出，但似乎有bug。可参考：https://platform.moonshot.cn/docs/api/partial
# role_assistant = {
#     "role": "assistant",
#     "name": role_name,
#     "content": "",
#     "partial": True,
# }

# # 输入文本（与助手对话）
# input_text = "你好，你是谁？详细告诉我一下你的情况吧。"

# completion = client.chat.completions.create(
#     model="moonshot-v1-8k",
#     messages=[
#         {"role": "system",
#          "content": role_setting},
#         {"role": "user", "content": input_text},
#     ],
#     temperature=0.8,
# )
#
# # 通过 API 我们获得了 Kimi 大模型给予我们的回复消息（role=assistant）
# print(completion.choices[0].message.content)

history = [
    role_system,  # 角色设定提示
    # role_assistant  # 预填
]


def chat(query, history):
    history.append({
        "role": "user",
        "content": query
    })
    completion = client.chat.completions.create(
        model="moonshot-v1-8k",
        messages=history,
        temperature=0.8,
    )
    result = completion.choices[0].message.content
    history.append({
        "role": "assistant",
        "content": result
    })
    return result


print(chat("你好，你是谁？详细告诉我一下你的情况吧。？", history))
# print(chat("你怎么看待特蕾西娅和阿米娅？", history))

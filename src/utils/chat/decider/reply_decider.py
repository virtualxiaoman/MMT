import warnings
from pathlib import Path
import ollama
import re
import random

from src.config.QQ_bot_info_loader import BotConfig
from src.config.path import PROMPT_DIR
from src.utils.chat.role_chat import ChatDSAPI
from src.config.models import model_settings
from src.utils.tools.file import load_from_txt

NO_REPLY_MESSAGES = [
    "呐，Coins-5 ~",
    "呆毛你好可爱吖",
]


class ReplyDecider:
    def __init__(self, config: BotConfig, model_name=None):
        """
        初始化判决器
        :param model_name: 本地部署的 ollama 模型名称
        """
        self.name_zh = config.name_zh
        self.name_en = config.name_en
        self.nickname = config.nickname
        self.qq_id = config.qq_id
        if model_name is None:
            self.model_name = model_settings.decide.get("name")
        else:
            self.model_name = model_name

        path = Path(PROMPT_DIR) / f"{self.name_en}.txt"
        bot_role_prompt = ""
        if not path.exists():
            warnings.warn(f"角色设定提示词文件 {path} 不存在")
        else:
            bot_role_prompt = load_from_txt(path)

        prompt = f"""你是一个专门用于判断群聊消息是否需要用户回复的AI助手。
该用户的名字是 "{self.name_zh}" 或者 "{self.name_en}"，昵称有{'、'.join(self.nickname)}"。
其人设是{bot_role_prompt}
请仔细阅读给出的群聊消息上下文，并判断用户是否应该在此时发言。
判断规则：
1. 如果最新消息明确提到了该用户（昵称、名字、@等），输出 True。
2. 如果最新消息是在向该用户提问、请求帮助、等待该用户回应，输出 True。
3. 如果该用户之前参与了当前话题，而其他成员正在回复该用户的内容，输出 True。
4. 如果该用户长时间未发言，但当前话题与该用户明显相关（例如图片中的人物是该用户或者文字提及了该人物），且能够自然参与讨论，可输出 True。
5. 对于普通闲聊、群成员之间的对话、与该用户无关的话题，输出 False。
6. 不要为了维持活跃度而主动发言。
7. 不要因为聊天进行了若干条消息就自动加入。
8. 除非存在明确的发言理由，否则默认输出 False。
9. 宁可错过一次发言机会，也不要频繁打扰群聊。
10. 当无法确定是否应该发言时，优先输出 False。
输出要求：
只能输出：
True
或
False
不要输出任何其他内容。"""
        # 初始化多轮对话的历史记忆，系统提示词定调
        self.history = [
            {
                "role": "system",
                "content": (
                    prompt
                    # f"你是一个专门用于判断群聊消息是否需要用户回复的AI助手。该用户的名字是 '{self.name}'。"
                    # "仔细阅读给出的群聊消息上下文。"
                    # "如果最新的一条消息是向该用户对话、或者结合上下文判断应该需要该用户参与和回复，请严格输出 'True'。"
                    # "对于其他人的闲聊，可以判断时机适时加入话题中，此时请严格输出 'True'。"
                    # "但如果不需要该用户插话，请严格输出 'False'。"
                    # "一般而言当其他人聊5~8句你就可以适当加入一次（严格输出 'True'），保持活跃度."
                    # "但也不要过于频繁以免打扰別人了。也就是除非你觉得非常有必要，否则不要连续回复（严格输出 'False'）。"
                    # "注意：你的回复只能包含 'True' 或 'False'，不要输出任何额外的标点符号、解释或说明。"
                )
            }
        ]
        self.options_local = {
            # 常用采样控制
            "temperature": 0.8,
            "top_p": 0.9,
            "top_k": 40,
            # 生成长度 / 上下文
            "num_predict": 2048,  # 要求返回的最大 token 数（名称/行为视版本）
            "num_ctx": 65536,  # 如果模型支持，扩展上下文窗口
            # 减少重复
            "repeat_penalty": 1.1,
            "repeat_last_n": 64,
        }
        self.chat_ds = ChatDSAPI()

    def _parse_response(self, response_text: str) -> bool:
        """
        辅助函数：处理大模型的输出，确保能正确解析出 True 或 False
        """
        text = response_text.strip().lower()

        # 使用正则寻找文本中的 true 或 false，防止模型输出包含额外字符（如 "True."）
        if re.search(r'\btrue\b', text):
            return True
        elif re.search(r'\bfalse\b', text):
            return False

        # 兜底策略：如果模型抽风既没说 True 也没说 False，以20%的概率返回 True，80%概率返回 False，保持谨慎态度
        return random.random() < 0.2  # 20%概率返回 True

    def check_if_should_reply(self, user_text: str) -> bool:
        """
        传入最新的一条消息，存入历史记录，并调用大模型判断是否需要回复
        """
        # return False
        # print(user_text)
        if not user_text:
            return False
        if user_text in NO_REPLY_MESSAGES:
            print(f"[ReplyDecider] 消息 '{user_text}' 在 NO_REPLY_MESSAGES 列表中，直接返回 False")
            return False
        # 1. 将最新的群聊消息加入历史记忆
        self.history.append({
            "role": "user",
            "content": f"最新群聊消息：{user_text}"  # todo: 加入发送者
        })

        # 2. 检测文本中是否含有字符串"[CQ:at,qq=self.qq_id]"，如果有则直接返回 True
        if (
                f"@{self.qq_id}" in user_text
                or f"[CQ:at,qq={self.qq_id}]" in user_text
                or f'At(qq="{self.qq_id}")' in user_text
        ):
            self.history.append({
                "role": "assistant",
                "content": "True"
            })
            print(f"[ReplyDecider] 消息 @了{self.qq_id}，直接返回 True")
            return True

        try:
            # model_name = model_settings.decide.get("name")
            model_type = model_settings.decide.get("type")

            if model_type == "local":
                # 3. 调用 ollama 接口进行预测
                response = ollama.chat(
                    model=self.model_name,
                    messages=self.history,
                    options=self.options_local
                )
                reply_content = response['message']['content']
                print(f"[ReplyDecider-本地模型]{self.name_zh}认为是否需要回复的原始模型输出: '{reply_content}'")
                needs_reply = self._parse_response(reply_content)
                # 4. 将助手的判断也存入历史，维持标准的多轮对话格式 (User -> Assistant -> User -> ...)
                self.history.append({
                    "role": "assistant",
                    "content": "True" if needs_reply else "False"  # 存入标准布尔字符串，帮助模型在后续对话中保持格式一致性
                })

            else:
                # 初始self.msg = []，此时才要copy
                if not self.chat_ds.msg:
                    print(f"[ReplyDecider-API模型]首次调用，正在将提示词传入 ChatDSAPI 实例...")
                    self.chat_ds.msg = self.history.copy()  # 将当前历史传入 ChatDSAPI 实例
                reply_content = self.chat_ds.one_chat(user_text)
                print(f"[ReplyDecider-API模型]{self.name_zh}认为是否需要回复的原始模型输出: '{reply_content}'")
                needs_reply = self._parse_response(reply_content)
                self.history = self.chat_ds.msg.copy()  # 将 ChatDSAPI 实例的历史覆盖回来，保持两者同步

            return needs_reply

        except Exception as e:
            print(f"[ReplyDecider] 调用 Ollama 模型时发生错误: {e}")
            # 如果模型调用失败，可以把刚刚加入的 user_text 弹出来，以免破坏历史记录状态
            self.history.pop()
            return False

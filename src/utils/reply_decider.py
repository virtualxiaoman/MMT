import ollama
import re
import random

from src.utils.chat import ChatDSAPI

from src.config.models import model_settings


class ReplyDecider:
    def __init__(self, name, qq_id, model_name=None):
        """
        初始化判决器
        :param model_name: 本地部署的 ollama 模型名称
        :param name: 你在群聊中的昵称或标识，帮助模型识别是否在叫你
        """
        self.name = name
        self.qq_id = qq_id
        if model_name is None:
            self.model_name = model_settings.decide.get("name")

        # 初始化多轮对话的历史记忆，系统提示词定调
        self.history = [
            {
                "role": "system",
                "content": (
                    f"你是一个专门用于判断群聊消息是否需要用户回复的AI助手。该用户的名字是 '{self.name}'。"
                    "仔细阅读给出的群聊消息上下文。"
                    "如果最新的一条消息是向该用户对话、或者结合上下文判断应该需要该用户参与和回复，请严格输出 'True'。"
                    "对于其他人的闲聊，可以判断时机适时加入话题中，此时请严格输出 'True'。"
                    "但如果不需要该用户插话，请严格输出 'False'。"
                    "一般而言当其他人聊5~8句你就可以适当加入一次（严格输出 'True'），保持活跃度."
                    "但也不要过于频繁以免打扰別人了。也就是除非你觉得非常有必要，否则不要连续回复（严格输出 'False'）。"
                    "注意：你的回复只能包含 'True' 或 'False'，不要输出任何额外的标点符号、解释或说明。"
                )
            }
        ]
        self.options = {
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
        if not user_text:
            return False
        # 1. 将最新的群聊消息加入历史记忆
        self.history.append({
            "role": "user",
            "content": f"最新群聊消息：{user_text}"
        })

        # 2. 检测文本中是否含有字符串"[CQ:at,qq=self.qq_id]"，如果有则直接返回 True
        if f"[CQ:at,qq={self.qq_id}]" in user_text:
            self.history.append({
                "role": "assistant",
                "content": "True"
            })
            return True

        try:
            # model_name = model_settings.decide.get("name")
            model_type = model_settings.decide.get("type")

            if model_type == "local":
                # 3. 调用 ollama 接口进行预测
                response = ollama.chat(
                    model=self.model_name,
                    messages=self.history,
                    options=self.options
                )
                reply_content = response['message']['content']
                print(f"[ReplyDecider-本地模型]{self.name}认为是否需要回复的原始模型输出: '{reply_content}'")
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
                print(f"[ReplyDecider-API模型]{self.name}认为是否需要回复的原始模型输出: '{reply_content}'")
                needs_reply = self._parse_response(reply_content)
                self.history = self.chat_ds.msg.copy()  # 将 ChatDSAPI 实例的历史覆盖回来，保持两者同步

            return needs_reply

        except Exception as e:
            print(f"[ReplyDecider] 调用 Ollama 模型时发生错误: {e}")
            # 如果模型调用失败，可以把刚刚加入的 user_text 弹出来，以免破坏历史记录状态
            self.history.pop()
            return False

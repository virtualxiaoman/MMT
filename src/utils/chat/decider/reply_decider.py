import json
import warnings
from pathlib import Path
import ollama
import re
import random
from dataclasses import dataclass, field
from typing import Literal

from src.config.QQ_bot_info_loader import BotConfig
from src.config.path import PROMPT_DIR, API_KEY_DIR
from src.utils.chat.llm.llm_chat import LLMDSAPI
from src.utils.chat.manager.conversation import ConversationManager
from src.utils.chat.model_type import LLMModelType
from src.utils.chat.role_chat import ChatDSAPI
from src.config.models import model_settings
from src.utils.tools.file import load_from_txt

NO_REPLY_MESSAGES = [
    "呐，Coins-5 ~",
    "呆毛你好可爱吖",
]


@dataclass(slots=True, frozen=True)
class ReplyDecisionData:
    """
    第一阶段（Reply Decision）的输出。

    用于判断当前是否应该回复，不包含具体回复内容。
    """

    Decision = Literal[
        "required",  # required: 必须回复
        "optional",  # optional: 可以回复，由程序根据 probability 决定是否回复
        "skip",  # skip: 不应回复
    ]

    Type = Literal[
        "at",  # at: 被 @
        "mention",  # mention: 被提及名字或昵称
        "question",  # question: 被提问、征求意见
        "reply_to_me",  # reply_to_me: 当前消息是在回复机器人上一条消息
        "request",  # request: 请求机器人帮助
        "related_topic",  # related_topic: 当前话题与角色高度相关
        "greeting",  # greeting: 打招呼
        "farewell",  # farewell: 告别
        "invitation",  # invitation: 邀请加入讨论
        "emotional_topic",  # emotional_topic: 当前适合表达情绪
        "silence_gap",  # silence_gap: 聊天出现短暂停顿，可自然插话
    ]

    Goal = Literal[
        "information",  # information: 提供事实或知识
        "opinion",  # opinion: 表达观点
        "emotion",  # emotion: 表达情绪
        "humor",  # humor: 幽默、玩梗
        "encouragement",  # encouragement: 鼓励、安慰
        "greeting",  # greeting: 打招呼
        "continue_topic",  # continue_topic: 延续当前话题
        "question",  # question: 提出新的问题
        "experience",  # experience: 分享符合角色设定的经历
    ]

    Stage = Literal[
        "opening",  # opening: 话题刚开始
        "active",  # active: 聊天进行中
        "ending",  # ending: 话题接近结束
    ]

    Stability = Literal[
        "new",  # new: 新话题，讨论尚未稳定
        "stable",  # stable: 已形成稳定讨论
    ]

    # 回复决策
    needs_reply: Decision = "skip"
    # 回复概率（0~1）：optional 时通常直接作为回复概率；required/skip默认回复/不回复而不使用概率
    probability: float = 0.0
    # 判定原因，用于日志和调试。
    reason: str = ""
    # 回复触发类型（允许多个）
    reply_types: list[Type] = field(default_factory=list)
    # 本次回复希望达到的目标
    reply_goal: Goal = "emotion"
    # 当前聊天阶段
    conversation_stage: Stage = "active"
    # 当前话题稳定程度
    topic_stability: Stability = "stable"


class ReplyDecider:
    def __init__(self, config: BotConfig, model_name: str = LLMModelType.DS_FLASH.value):
        """
        初始化判决器
        """
        self.name_zh = config.name_zh
        self.name_en = config.name_en
        self.nickname = config.nickname
        self.bot_id = config.bot_id
        self.model_name = model_name
        self._init_prompt()

    def _init_prompt(self):
        path = Path(PROMPT_DIR) / f"{self.name_en}_reply_decision.txt"
        bot_role_prompt = ""
        if not path.exists():
            warnings.warn(f"角色设定提示词文件 {path} 不存在")
        else:
            bot_role_prompt = load_from_txt(path)

        prompt = f"""你是一个专门用于判断群聊消息是否需要用户回复的AI助手。
该用户的名字是 "{self.name_zh}" 或者 "{self.name_en}"，昵称有{'、'.join(self.nickname)}"。
该用户的人设如下：\n{bot_role_prompt}
请仔细阅读给出的群聊消息上下文，并判断用户是否应该在此时发言。
判断规则：
你的任务不是生成回复，而是判断：
当前是否存在一个自然、合理、不突兀的发言机会。
请遵循以下规则。
【required】需要回复，满足以下任意情况：
- 最新消息 @ 了该用户{self.bot_id}或者明确提到了该用户名字或昵称{self.name_zh}、{self.name_en}、{'、'.join(self.nickname)}
- 有人在向该用户提问或者请求该用户帮助或者等待该用户回答
- 当前消息是在回复该用户之前的发言
此时 needs_reply 输出 required。
【optional】可选回复，满足以下情况之一即可：
- 当前话题与该用户人设高度相关
- 当前话题属于该用户自然会参与的话题
- 当前聊天存在开放式讨论
- 当前消息留下了自然接话空间
- 当前聊天节奏较平缓，不会打断别人
- 可以自然表达观点、情绪、吐槽或补充信息
- 聊天出现短暂停顿，可以自然加入
此时 needs_reply 输出 optional。
【skip】不要回复，包括但不限于：
- 当前聊天与该用户完全无关
- 两三个人正在连续只与对方聊天，插话会打断别人
- 当前没有自然切入点
- 回复只是为了维持活跃度
- 完全无法确定是否应该发言
此时 needs_reply 输出 skip。

输出要求：请输出 JSON。
示例格式如下：
{{
    "needs_reply": "optional",
    "probability": 0.72,
    "reason": "一句简短原因，说明为什么需要回复，可以回复什么方向的内容",
    "reply_types": [
        "mention",
        "related_topic"
    ],
    "reply_goal": "opinion",
    "conversation_stage": "active",
    "topic_stability": "stable"
}}
字段说明（这些字段只能使用以下指定的英文值，后面的中文是其意思的注释）：
needs_reply: required：必须回复，optional：可以回复，skip：不回复。
probability: 0~1。当 needs_reply 为 optional 时，会将probability直接作为回复概率。
reply_types: 可以包含多个值：at: 被 @、 mention: 被提及名字或昵称、question: 被提问、征求意见、reply_to_me: 当前消息是在回复机器人上一条消息、request: 请求机器人帮助、related_topic: 当前话题与角色高度相关、greeting: 打招呼、arewell: 告别、invitation: 邀请加入讨论、emotional_topic: 当前适合表达情绪、silence_gap: 聊天出现短暂停顿，可自然插话
reply_goal: 回复希望达到的目标：information: 提供事实或知识、opinion: 表达观点、emotion: 表达情绪、humor: 幽默、玩梗、encouragement: 鼓励、安慰、greeting: 打招呼、continue_topic: 延续当前话题、question: 提出新的问题、experience: 分享符合角色设定的经历
conversation_stage: opening: 话题刚开始、active: 聊天进行中、ending: 话题接近结束。
topic_stability: new: 新话题，讨论尚未稳定、stable: 已形成稳定讨论。
不要输出 Markdown，不要输出解释，不要输出 ```json，只输出 JSON。

以下是最新的群聊记录，你要根据这一段聊天记录判断接下来用户是否需要发言：

"""
        # 1. 如果最新消息明确提到了该用户（昵称、名字、@等），输出 True。
        # 2. 如果最新消息是在向该用户提问、请求帮助、等待该用户回应，输出 True。
        # 3. 如果该用户之前参与了当前话题，而其他成员正在回复该用户的内容，输出 True。
        # 4. 如果该用户长时间未发言，但当前话题与该用户明显相关（例如图片中的人物是该用户或者文字提及了该人物），且能够自然参与讨论，可输出 True。
        # 5. 对于普通闲聊、群成员之间的对话、与该用户无关的话题，输出 False。
        # 6. 不要为了维持活跃度而主动发言。
        # 7. 不要因为聊天进行了若干条消息就自动加入。
        # 8. 除非存在明确的发言理由，否则默认输出 False。
        # 9. 宁可错过一次发言机会，也不要频繁打扰群聊。
        # 10. 当无法确定是否应该发言时，优先输出 False。
        # 初始化多轮对话的历史记忆，系统提示词定调
        self.system_prompt = prompt
        # self.history = [
        #     {
        #         "role": "system",
        #         "content": (
        #             prompt
        #             # f"你是一个专门用于判断群聊消息是否需要用户回复的AI助手。该用户的名字是 '{self.name}'。"
        #             # "仔细阅读给出的群聊消息上下文。"
        #             # "如果最新的一条消息是向该用户对话、或者结合上下文判断应该需要该用户参与和回复，请严格输出 'True'。"
        #             # "对于其他人的闲聊，可以判断时机适时加入话题中，此时请严格输出 'True'。"
        #             # "但如果不需要该用户插话，请严格输出 'False'。"
        #             # "一般而言当其他人聊5~8句你就可以适当加入一次（严格输出 'True'），保持活跃度."
        #             # "但也不要过于频繁以免打扰別人了。也就是除非你觉得非常有必要，否则不要连续回复（严格输出 'False'）。"
        #             # "注意：你的回复只能包含 'True' 或 'False'，不要输出任何额外的标点符号、解释或说明。"
        #         )
        #     }
        # ]
        # self.client = OpenAI(
        #     api_key=load_from_txt(Path(API_KEY_DIR) / "deepseek.txt"),
        #     base_url="https://api.deepseek.com"
        # )
        self.llm = LLMDSAPI(
            model=self.model_name,
            response_format={
                "type": "json_object"
            },
            temperature=0.3,
            max_tokens=8192
        )

    @staticmethod
    def _parse_response(response_text: str) -> ReplyDecisionData:
        """
        解析模型 JSON 输出。
        """
        try:
            data = json.loads(response_text)
            return ReplyDecisionData(
                needs_reply=data.get("needs_reply", "skip"),
                probability=float(data.get("probability", 0.0)),
                reason=str(data.get("reason", "")).strip(),
                reply_types=list(data.get("reply_types", [])),
                reply_goal=data.get("reply_goal", "emotion"),
                conversation_stage=data.get("conversation_stage", "active"),
                topic_stability=data.get("topic_stability", "stable"),
            )

        except Exception as e:
            print(f"[ReplyDecider] JSON解析失败：{e}")
            print(f"[ReplyDecider] 原始输出：\n{response_text}")
            return ReplyDecisionData(
                needs_reply="skip",
                probability=0.0,
                reason="JSON解析失败",
            )
        # try:
        #     data = json.loads(response_text)
        #     return ReplyDecisionData(needs_reply=bool(data.get("reply", False)),
        #                              reason=str(data.get("reason", "")).strip())
        # except Exception as e:
        #     print("[ReplyDecider] JSON解析失败：", e)
        #     text = response_text.lower()
        #     if re.search(r"\btrue\b", text):
        #         return ReplyDecisionData(True, "JSON解析失败，降级匹配True")
        #     if re.search(r"\bfalse\b", text):
        #         return ReplyDecisionData(False, "JSON解析失败，降级匹配False")
        #     return ReplyDecisionData(random.random() < 0.2, "模型输出异常，采用随机兜底策略")

    def _call_deepseek(self, chat_context: str) -> ReplyDecisionData:
        """
        调用 DeepSeek JSON Output
        """
        # # 修改：每次重新构造 messages，不再使用 self.history
        # messages = [
        #     {
        #         "role": "system",
        #         "content": self.system_prompt,
        #     },
        #     {
        #         "role": "user",
        #         "content": chat_context,
        #     }
        # ]
        conv = ConversationManager(
            system_prompt=self.system_prompt,
            enable_memory=False,
        )
        conv.add_user(chat_context)
        reply_content = self.llm.one_chat(conv.messages)
        # response = self.client.chat.completions.create(
        #     model=self.model_name,
        #     messages=messages,
        #     response_format={
        #         "type": "json_object"
        #     },
        #     temperature=0.3,
        #     max_tokens=8192
        # )
        #
        # reply_content = response.choices[0].message.content
        #
        # # print(
        # #     f"[ReplyDecider-API] 原始输出：\n{reply_content}"
        # # )

        decision = self._parse_response(reply_content)

        # self.history.append({
        #     "role": "assistant",
        #     "content": reply_content
        # })

        print(f"[ReplyDecider] {self.name_zh}: "
              f"needs_reply={decision.needs_reply}",
              f"probability={decision.probability:.2f}",
              f"reply_types={decision.reply_types}\n",
              f"reply_goal={decision.reply_goal}",
              f"conversation_stage={decision.conversation_stage}",
              f"topic_stability={decision.topic_stability}",
              f"reason={decision.reason}")

        return decision

    def check_if_should_reply(self, latest_msg: str, history_msg: str) -> ReplyDecisionData:
        """
        判断当前群聊消息是否存在自然发言机会。

        Parameters
        ----------
        latest_msg : str
            群聊上下文（包含最新消息）。

        Returns
        -------
        ReplyDecisionData
            回复判定结果。
        """
        if not latest_msg:
            return ReplyDecisionData(
                needs_reply="skip",
                probability=0.0,
                reason="消息为空",
            )

        if latest_msg in NO_REPLY_MESSAGES:
            print(f"[ReplyDecider] 消息 '{latest_msg}' 位于 NO_REPLY_MESSAGES 中，跳过判定。")
            return ReplyDecisionData(
                needs_reply="skip",
                probability=0.0,
                reason="消息位于忽略列表",
            )

            # 优先检测 @
        if (
                f"@{self.bot_id}" in latest_msg
                or f"[CQ:at,qq={self.bot_id}]" in latest_msg
                or f'At(qq="{self.bot_id}")' in latest_msg
        ):
            print(f"[ReplyDecider] 检测到 @{self.bot_id}，直接判定 required。")

            return ReplyDecisionData(
                needs_reply="required",
                probability=1.0,
                reason=f"检测到@{self.bot_id}",
                reply_types=["at"],
                reply_goal="information",
                conversation_stage="active",
                topic_stability="stable",
            )

        # self.history.append({
        #     "role": "user",
        #     "content": latest_msg,
        # })
        chat_context = ""
        if history_msg:
            chat_context += f"最近聊天记录：\n{history_msg}"
        chat_context += f"最新一条聊天记录：\n{latest_msg}"
        try:
            return self._call_deepseek(chat_context)

        except Exception as e:
            print(f"[ReplyDecider] 调用模型失败：{e}")

            return ReplyDecisionData(
                needs_reply="skip",
                probability=0.0,
                reason="模型调用失败",
            )
        # if not user_text:
        #     return ReplyDecisionData(needs_reply=False, reason="消息为空")
        #
        # if user_text in NO_REPLY_MESSAGES:
        #     print(f"[ReplyDecider] 消息 '{user_text}' 在 NO_REPLY_MESSAGES 中，直接返回 False")
        #     return ReplyDecisionData(needs_reply=False, reason="消息位于忽略列表")
        #
        # # 直接检测 @
        # if (
        #         f"@{self.qq_id}" in user_text
        #         or f"[CQ:at,qq={self.qq_id}]" in user_text
        #         or f'At(qq="{self.qq_id}")' in user_text
        # ):
        #     print(f"[ReplyDecider] 检测到 @ {self.qq_id}，直接回复。")
        #     return ReplyDecisionData(needs_reply=True, reason=f"检测到@{self.qq_id}")
        #
        # try:
        #     decision = self._call_deepseek()
        #     return decision
        # except Exception as e:
        #     print(f"[ReplyDecider] 调用模型失败：{e}")
        #     return ReplyDecisionData(needs_reply=False, reason="模型调用失败")

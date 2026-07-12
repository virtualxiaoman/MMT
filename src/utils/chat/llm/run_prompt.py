from __future__ import annotations

from src.utils.chat.llm.llm_chat import LLMDSAPI
from src.utils.chat.manager.conversation import ConversationManager
from src.utils.chat.model_type import LLMModelType


class PromptRunner:
    """
    Prompt 执行器。

    本类用于执行一次性的 Prompt。

    适用于：

        - Summary
        - Knowledge 检索
        - Emotion 判断
        - Prompt 分类
        - Memory 压缩
        - Prompt Router
        - 任意一次性 LLM 调用

    不负责：

        - 多轮聊天
        - Conversation Memory
        - Prompt 拼接
        - 文件管理
    """

    def __init__(
            self,
            model: LLMModelType = LLMModelType.DS_FLASH,
    ) -> None:
        """
        Parameters
        ----------
        model
            默认模型。
        """

        self._llm = LLMDSAPI(
            model=model,
        )

    def run(
            self,
            system_prompt: str,
            user_prompt: str,
    ) -> str:
        """
        执行一次 Prompt。

        Parameters
        ----------
        system_prompt
            System Prompt。

        user_prompt
            User Prompt。

        Returns
        -------
        str
            LLM 返回结果。
        """

        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        if not system_prompt:
            raise ValueError("system_prompt 不能为空。")

        if not user_prompt:
            return ""

        conv = ConversationManager(
            system_prompt=system_prompt,
            enable_memory=False,
        )

        conv.add_user(user_prompt)

        reply = self._llm.one_chat(
            conv.messages,
        )

        return reply.strip()

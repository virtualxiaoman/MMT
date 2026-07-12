from __future__ import annotations
from typing import Union
from openai.types.chat import ChatCompletionMessage
from copy import deepcopy

MessageType = Union[
    dict,
    ChatCompletionMessage,
]


class ConversationManager:
    """
    对话管理器。

    职责：
        - 保存 messages
        - 保存 system prompt
        - 管理历史记录

    不负责：
        - 调用 LLM
        - Prompt 加载
        - Tool Calling
    """

    def __init__(
            self,
            system_prompt: str | None = None,
            enable_memory: bool = True,
    ):
        """
        Parameters
        ----------
        system_prompt
            System Prompt。

        enable_memory
            是否保存历史聊天记录。
        """

        self.enable_memory = enable_memory

        self._system_prompt = system_prompt

        self._messages: list[MessageType] = []

        self._reset()

    @property
    def messages(self) -> list[MessageType]:
        """
        返回 messages。

        返回 deepcopy，避免外部直接修改内部状态。
        """

        return deepcopy(self._messages)

    def add_user(self, text: str):
        """
        添加用户消息。
        """

        if not self.enable_memory:
            self._reset()

        self._messages.append({
            "role": "user",
            "content": text
        })

    def add_system(self, text: str):
        """
        添加新的 System Prompt。

        会覆盖旧 Prompt。
        """

        self._system_prompt = text
        self._reset()

    def add_assistant(self, message: str | ChatCompletionMessage):
        """
        添加 Assistant 消息。

        Parameters
        ----------
        message
            OpenAI SDK 返回的
            ChatCompletionMessage。

            推荐直接传：

                response.choices[0].message
        原有实现为：
            def add_assistant(self, text: str):
                if not self.enable_memory:
                    return

                self._messages.append({
                    "role": "assistant",
                    "content": text
                })
        """

        if not self.enable_memory:
            return
        if isinstance(message, str):
            message = {
                "role": "assistant",
                "content": message
            }
        elif isinstance(message, ChatCompletionMessage):
            pass
        else:
            raise ValueError(
                f"message 必须是 str 或 ChatCompletionMessage，"
                f"当前类型为 {type(message)}"
            )
        self._messages.append(message)

    def clear(self):
        """
        清空历史，仅保留 System Prompt。
        """

        self._reset()

    def pop_last(self):
        """
        删除最后一条消息。

        一般用于 Tool Calling 出错回滚。
        """

        if len(self._messages) == 0:
            return

        if (
                len(self._messages) == 1
                and self._messages[0].get("role") == "system"
        ):
            return

        self._messages.pop()

    def _reset(self):
        """
        重置消息。

        保留 System Prompt。
        """

        self._messages.clear()

        if self._system_prompt is not None:
            self._messages.append({
                "role": "system",
                "content": self._system_prompt
            })

    def __len__(self):
        return len(self._messages)

    def __iter__(self):
        return iter(self._messages)

    def __repr__(self):
        return f"Conversation(messages={len(self._messages)})"

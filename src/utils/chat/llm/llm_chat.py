from pathlib import Path
from openai import OpenAI

from src.config.path import API_KEY_DIR
from src.utils.chat.manager.conversation import ConversationManager
from src.utils.chat.model_type import LLMModelType
from src.utils.tools.file import load_from_txt


class LLMDSAPI:
    """
    DeepSeek API 封装。

    本类仅负责：
        messages
            ↓
        DeepSeek API
            ↓
        reply

    不负责：
        - Prompt
        - Conversation
        - Role
        - History
    """

    def __init__(
            self,
            model: LLMModelType | str = LLMModelType.DS_PRO,
            enable_reasoning: bool = False,
            reasoning_effort: str = "high",
            response_format: dict | None = None,
            api_key_path: str | Path | None = None,
            temperature: float = 1.3,
            max_tokens: int = 8192
    ):
        """
        Parameters
        ----------
        model
            使用的 DeepSeek 模型。

        enable_reasoning
            是否开启思考模式。

        reasoning_effort
            思考强度。
            可选：
                "high"
                "max"

        api_key_path
            API Key 文件。


        temperature
            温度。
            注意：
                DeepSeek 思考模式下 temperature 不生效，
                这里只用于非思考模式。
        """

        if api_key_path is None:
            api_key_path = Path(API_KEY_DIR) / "deepseek.txt"

        self.client = OpenAI(
            api_key=load_from_txt(api_key_path),
            base_url="https://api.deepseek.com",
        )
        if isinstance(model, LLMModelType):
            self.model = model.value
        elif isinstance(model, str):
            self.model = model
        else:
            raise ValueError(f"model: {type(model)}类型错误")
        self.enable_reasoning = enable_reasoning
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.response_format = response_format

    # ------------------------------------------------------------------

    def one_chat(self, messages: list[dict]) -> str:
        """
        普通聊天。

        Parameters
        ----------
        messages
            OpenAI 格式 messages。

        Returns
        -------
        str
            模型最终回答（content）。
        """

        message = self.one_chat_raw(messages)

        return message.content or ""

    # ------------------------------------------------------------------

    def one_chat_raw(self, messages: list[dict]):
        """
        返回完整 Assistant Message。

        Tool Calling、思考模式建议使用本接口。

        Returns
        -------
        ChatCompletionMessage
        """

        kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        # --------------------------
        # 非思考模式
        # --------------------------

        if not self.enable_reasoning:
            kwargs["temperature"] = self.temperature

        # --------------------------
        # 思考模式
        # --------------------------

        else:
            kwargs["reasoning_effort"] = self.reasoning_effort

            kwargs["extra_body"] = {
                "thinking": {
                    "type": "enabled"
                }
            }

        if self.response_format:
            kwargs["response_format"] = self.response_format

        if isinstance(self.max_tokens, int) and self.max_tokens > 0:
            kwargs["max_tokens"] = self.max_tokens

        response = self.client.chat.completions.create(**kwargs)

        return response.choices[0].message


def test1(prompt):
    conv = ConversationManager(
        system_prompt=prompt,
        enable_memory=False,
    )

    llm = LLMDSAPI(
        model=LLMModelType.DS_FLASH,
    )

    conv.add_user("你好")

    reply = llm.one_chat(conv.messages)
    conv.add_user("今天星期几")
    print(reply)
    reply = llm.one_chat(conv.messages)
    print(reply)


def test2(prompt):
    conv = ConversationManager(
        system_prompt=prompt,
        enable_memory=True,
    )

    llm = LLMDSAPI(
        model=LLMModelType.DS_PRO,
    )

    conv.add_user("你好")

    reply = llm.one_chat(conv.messages)
    print(reply)

    conv.add_assistant(reply)
    conv.add_user("再说一遍")

    reply = llm.one_chat(conv.messages)
    print(reply)
    conv.add_assistant(reply)


if __name__ == "__main__":
    prompt = "你是洛天依"
    test1(prompt)
    test2(prompt)

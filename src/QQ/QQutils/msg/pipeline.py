from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.QQ.QQutils.res.history_loader import HistoryLoader
# from src.QQ.QQutils.msg.msgctx import MessageContext
from src.config.path import PROMPT_DIR
from src.utils.chat.history.manage_summary import SummaryManager, SummaryGenerator
from src.utils.chat.llm.llm_chat import LLMDSAPI
from src.utils.chat.llm.run_prompt import PromptRunner
from src.utils.chat.manager.conversation import ConversationManager
from src.utils.chat.model_type import LLMModelType
from src.utils.chat.prompt.load_prompt import KnowledgeLoader, KnowledgeRetriever
from src.utils.tools.file import load_from_txt


class ChatPipeline:
    """
    AI聊天总流程控制器

    负责连接：

        用户输入
            |
            v
        Memory
            |
            v
        Knowledge
            |
            v
        Conversation
            |
            v
        LLM
            |
            v
        Reply


    本类不负责：
        - LLM实现
        - 知识库实现
        - 总结算法
        - Prompt生成细节

    只负责流程编排。
    """

    def __init__(
            self,
            *,
            bot_id: int,
            is_private: bool,
            session_id: str,
            system_prompt: str,
            name_en: Optional[str] = None,
            memory_manager: Optional[SummaryManager] = None,
            name_zh: Optional[str] = None,
    ):

        self.bot_id = bot_id
        self.is_private = is_private
        self.session_id = session_id

        self.llm = LLMDSAPI(model=LLMModelType.DS_PRO)
        self.base_system_prompt = system_prompt
        self.memory_manager = memory_manager

        self.knowledge = None
        if name_en:
            self.knowledge = (KnowledgeLoader.load(name_en))
        self.name_zh = name_zh

    # ======================================================
    # 对外入口
    # ======================================================
    def chat(self, user_query: str) -> str:
        """
        完整聊天流程
        """
        # 1. 获取记忆
        memory_context = (self._get_memory())
        # 2. 知识检索
        knowledge_context = (self._retrieve_knowledge(user_query))
        # 3. 构造system prompt
        system_prompt = (self._build_system_prompt(memory_context, knowledge_context))
        # print(system_prompt)
        # 4. 创建Conversation
        conv = ConversationManager(system_prompt=system_prompt, enable_memory=False)
        # 5. 读取历史消息
        self._append_history(conv=conv)
        # # 6. 添加用户消息
        # conv.add_user(user_query)
        # 7. 调用LLM
        reply = self.llm.one_chat(conv.messages)
        return reply

    # ======================================================
    # Memory
    # ======================================================
    def _get_memory(self):
        if self.memory_manager is None:
            return None
        return {
            "long_term": self.memory_manager.load_long_term(),
            "short_term": self.memory_manager.load_short_term()
        }

    # ======================================================
    # Knowledge
    # ======================================================
    def _retrieve_knowledge(self, query: str):
        if self.knowledge is None:
            return None
        selector_prompt = (KnowledgeRetriever.build_prompt(query=query, knowledge=self.knowledge))
        selector_conv = ConversationManager(system_prompt=selector_prompt)
        selector_conv.add_user(query)
        selected_text = (self.llm.one_chat(selector_conv.messages))
        selected = (KnowledgeRetriever.parse_response(selected_text, self.knowledge))
        return selected

    # ======================================================
    # Prompt
    # ======================================================
    def _build_system_prompt(self, memory, knowledge):
        prompt = self.base_system_prompt
        if memory:
            prompt += f"\n\n以下是历史记忆:\n{memory}"
        if knowledge:
            prompt += f"\n\n以下是相关知识:\n{knowledge}"
        return prompt

    def _get_history(self) -> list[str]:
        return HistoryLoader.load_last_list(
            bot_id=self.bot_id,
            is_private=self.is_private,
            session_id=self.session_id,
            max_lines=50,
        )

    def _append_history(self, conv: ConversationManager) -> None:
        for msg in self._get_history():
            prefix, content = msg.split("：", 1)
            _, speaker = prefix.split("] ", 1)

            if speaker == self.name_zh:
                conv.add_assistant(content)
            else:
                conv.add_user(msg)


if __name__ == "__main__":
    prompt = load_from_txt(Path(PROMPT_DIR) / "LuoTianyi.txt")
    bot_id = 1121221045
    is_private = False
    session_id = "1039857271"
    runner = PromptRunner()
    generator = SummaryGenerator(
        runner
    )
    manager = SummaryManager(
        bot_id=bot_id,
        is_private=is_private,
        session_id=session_id,
        generator=generator,
    )
    llm = LLMDSAPI(
        model=LLMModelType.DS_PRO
    )

    pipeline = ChatPipeline(
        bot_id=bot_id,
        is_private=is_private,
        session_id=session_id,
        system_prompt=prompt,
        name_en="LuoTianyi",
        memory_manager=manager,
    )
    reply = pipeline.chat(
        "洛天依什么时候发布的V5声库"
    )
    print(reply)

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

# from src.QQ.QQutils.msg.msgctx import MessageContext
from src.config.QQ_bot_info_loader import BotConfig
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
            llm: LLMDSAPI,
            system_prompt: str,
            knowledge_name: Optional[str] = None,
            memory_manager: Optional[SummaryManager] = None,

    ):

        self.bot_id = bot_id
        self.is_private = is_private
        self.session_id = session_id

        self.llm = llm

        self.base_system_prompt = system_prompt

        self.knowledge_name = knowledge_name

        self.memory_manager = memory_manager

        # ============================
        # 初始化知识
        # ============================

        self.knowledge = None

        if knowledge_name:
            self.knowledge = (
                KnowledgeLoader.load(
                    knowledge_name
                )
            )

    # ======================================================
    # 对外入口
    # ======================================================

    def chat(
            self,
            user_query: str,
    ) -> str:
        """
        完整聊天流程
        """

        # --------------------------------
        # 1. 获取记忆
        # --------------------------------

        memory_context = (
            self._get_memory()
        )

        # --------------------------------
        # 2. 知识检索
        # --------------------------------

        knowledge_context = (
            self._retrieve_knowledge(
                user_query
            )
        )

        # --------------------------------
        # 3. 构造system prompt
        # --------------------------------

        system_prompt = (
            self._build_system_prompt(
                memory_context,
                knowledge_context,
            )
        )

        # --------------------------------
        # 4. 创建Conversation
        # --------------------------------

        conv = ConversationManager(
            system_prompt=system_prompt,
            enable_memory=False,
        )

        # --------------------------------
        # 5. 添加用户消息
        # --------------------------------

        conv.add_user(
            user_query
        )

        # --------------------------------
        # 6. 调用LLM
        # --------------------------------

        reply = (
            self.llm.one_chat(
                conv.messages
            )
        )

        # --------------------------------
        # 7. 保存上下文
        # --------------------------------

        # self._save_chat(
        #     user_query,
        #     reply,
        # )

        return reply

    # ======================================================
    # Memory
    # ======================================================

    def _get_memory(self):

        if self.memory_manager is None:
            return None

        return {

            "long_term":
                self.memory_manager.load_long_term(),

            "short_term":
                self.memory_manager.load_short_term(),

        }

    # ======================================================
    # Knowledge
    # ======================================================

    def _retrieve_knowledge(
            self,
            query: str,
    ):

        if self.knowledge is None:
            return None

        # 当前你的selector方案

        selector_prompt = (
            KnowledgeRetriever.build_prompt(
                query=query,
                knowledge=self.knowledge,
            )
        )

        selector_conv = ConversationManager(
            system_prompt=selector_prompt
        )

        selector_conv.add_user(
            query
        )

        selected_text = (
            self.llm.one_chat(
                selector_conv.messages
            )
        )

        selected = (
            KnowledgeRetriever.parse_response(
                selected_text,
                self.knowledge,
            )
        )

        return selected

    # ======================================================
    # Prompt
    # ======================================================

    def _build_system_prompt(
            self,
            memory,
            knowledge,
    ):

        prompt = self.base_system_prompt

        if memory:
            prompt += "\n\n"

            prompt += (
                "以下是历史记忆:\n"
            )

            prompt += str(memory)

        if knowledge:
            prompt += "\n\n"

            prompt += (
                "以下是相关知识:\n"
            )

            prompt += str(
                knowledge
            )

        return prompt

    # ======================================================
    # Save
    # ======================================================

    # def _save_chat(
    #         self,
    #         user,
    #         assistant,
    # ):
    #
    #     """
    #     保存聊天记录
    #
    #     这里不要做summary
    #
    #     只负责记录
    #
    #     """
    #
    #     if self.memory_manager is None:
    #         return
    #
    #     self.memory_manager.append(
    #         user,
    #         assistant,
    #     )


def chat_pipeline(name_en: str, bot_id: int, is_private: bool, session_id: str, query: str):
    path = Path(PROMPT_DIR) / f"{name_en}/role.txt"
    # print(f"绝对路径为：{path.resolve()}")
    if not path.exists():
        warnings.warn(f"角色设定提示词文件 {path} 不存在")
        return None
    else:
        role_prompt = load_from_txt(path)

    runner = PromptRunner()
    generator = SummaryGenerator(runner)
    manager = SummaryManager(bot_id=bot_id, is_private=is_private, session_id=session_id, generator=generator)
    llm = LLMDSAPI(model=LLMModelType.DS_PRO)

    pipeline = ChatPipeline(bot_id=bot_id, is_private=is_private, session_id=session_id, llm=llm,
                            system_prompt=role_prompt, knowledge_name=name_en, memory_manager=manager)
    reply = pipeline.chat(query)
    print(reply)
    return reply


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
        llm=llm,
        system_prompt=prompt,
        knowledge_name="LuoTianyi",
        memory_manager=manager,
    )
    reply = pipeline.chat(
        "洛天依什么时候发布的V5声库"
    )
    print(reply)

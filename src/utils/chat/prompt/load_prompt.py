from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from src.config.path import PROMPT_DIR
from src.utils.chat.llm.llm_chat import LLMDSAPI
from src.utils.chat.manager.conversation import ConversationManager
from src.utils.chat.model_type import LLMModelType
from src.utils.tools.file import load_from_txt


class RoleLoader:
    """
    角色 Prompt 加载器。

    功能：
        1. 根据角色名称读取对应目录下的 role.txt。
        2. 自动缓存已经读取过的角色 Prompt，避免重复访问磁盘。
        3. 提供统一接口，方便后续 PromptBuilder 调用。

    目录结构示例：

    prompt/
    ├── LuoTianyi/
    │   ├── role.txt
    │   └── knowledge/
    ├── Shiroko/
    │   ├── role.txt
    │   └── knowledge/
    └── ...

    使用方式：

        role_prompt = RoleLoader.load("LuoTianyi")

    第二次调用不会再次读取磁盘，而是直接返回缓存。
    """

    # role.txt 文件名
    ROLE_FILE_NAME = "role.txt"

    # 缓存：
    # key   -> 角色名称（例如 "LuoTianyi"）
    # value -> role.txt 内容
    _cache: dict[str, str] = {}

    @classmethod
    def load(cls, role_name: str) -> str:
        """
        加载指定角色的人设 Prompt。

        Parameters
        ----------
        role_name : str
            角色名称。
            例如：
                "LuoTianyi"

        Returns
        -------
        str
            role.txt 的完整内容。

        Raises
        ------
        FileNotFoundError
            对应角色目录不存在，
            或 role.txt 不存在。

        ValueError
            role_name 为空。
        """

        role_name = role_name.strip()

        if not role_name:
            raise ValueError("role_name不能为空。")

        # -----------------------------
        # 优先返回缓存
        # -----------------------------
        if role_name in cls._cache:
            return cls._cache[role_name]

        # -----------------------------
        # 拼接 role.txt 路径
        # -----------------------------
        role_path = (
                PROMPT_DIR
                / role_name
                / cls.ROLE_FILE_NAME
        )

        if not role_path.exists():
            raise FileNotFoundError(
                f"未找到角色 Prompt 文件：{role_path}"
            )

        # -----------------------------
        # 首次读取
        # -----------------------------
        role_prompt = load_from_txt(role_path)

        # 写入缓存
        cls._cache[role_name] = role_prompt

        return role_prompt

    @classmethod
    def clear_cache(cls) -> None:
        """
        清空所有缓存。

        一般用于：
            - 热更新 Prompt
            - 单元测试
            - 开发阶段重新加载 role.txt
        """
        cls._cache.clear()

    @classmethod
    def remove_cache(cls, role_name: str) -> None:
        """
        删除指定角色的缓存。

        Parameters
        ----------
        role_name : str
            角色名称。
        """
        cls._cache.pop(role_name, None)

    @classmethod
    def is_cached(cls, role_name: str) -> bool:
        """
        判断指定角色是否已经缓存。

        Returns
        -------
        bool
        """
        return role_name in cls._cache


@dataclass(slots=True)
class KnowledgeItem:
    """
    一个知识条目。
    """

    # 文件名（albums、relationship……）
    name: str
    # 检索摘要
    summary: str
    # 标签
    tags: list[str] = field(default_factory=list)
    # Prompt正文
    content: str = ""


class KnowledgeLoader:
    """
    知识库加载器。

    文件格式：

    summary: ......
    tag: 乐正绫
    tag: 言和
    content:
    xxxxx
    xxxxx

    返回：

    {
        "albums": KnowledgeItem(...),
        "relationship": KnowledgeItem(...),
        ...
    }

    每个角色仅加载一次，并缓存到内存。
    """

    KNOWLEDGE_DIR_NAME = "knowledge"

    _cache: dict[str, dict[str, KnowledgeItem]] = {}

    @classmethod
    def load(
            cls,
            role_name: str,
    ) -> dict[str, KnowledgeItem]:
        """
        加载指定角色全部知识。
        """

        role_name = role_name.strip()

        if not role_name:
            raise ValueError("role_name不能为空。")

        if role_name in cls._cache:
            return cls._cache[role_name]

        knowledge_dir = (
                PROMPT_DIR
                / role_name
                / cls.KNOWLEDGE_DIR_NAME
        )

        if not knowledge_dir.exists():
            raise FileNotFoundError(
                f"知识库目录不存在：{knowledge_dir}"
            )

        knowledge: dict[str, KnowledgeItem] = {}

        for file in sorted(knowledge_dir.glob("*.txt")):
            item = cls._load_file(file)

            knowledge[item.name] = item

        cls._cache[role_name] = knowledge

        return knowledge

    @staticmethod
    def _load_file(
            file_path: Path,
    ) -> KnowledgeItem:
        """
        读取单个知识文件。
        """

        lines = file_path.read_text(
            encoding="utf-8"
        ).splitlines()

        metadata: dict[str, object] = {}

        content_start = None

        for index, raw_line in enumerate(lines):

            line = raw_line.strip()

            if not line:
                continue

            # content:
            if line.lower() == "content:":
                content_start = index + 1
                break

            if ":" not in line:
                continue

            key, value = line.split(":", 1)

            key = key.strip().lower()
            value = value.strip()

            # tag 可以重复
            if key == "tag":
                metadata.setdefault("tags", [])
                metadata["tags"].append(value)
            else:
                metadata[key] = value

        if content_start is None:
            raise ValueError(
                f"{file_path} 缺少 content:。"
            )

        content = "\n".join(
            lines[content_start:]
        ).strip()

        return KnowledgeItem(
            name=file_path.stem,
            summary=str(metadata.get("summary", "")),
            tags=list(metadata.get("tags", [])),
            content=content,
        )

    @classmethod
    def clear_cache(cls):

        cls._cache.clear()

    @classmethod
    def remove_cache(
            cls,
            role_name: str,
    ):

        cls._cache.pop(role_name, None)

    @classmethod
    def is_cached(
            cls,
            role_name: str,
    ) -> bool:

        return role_name in cls._cache


class KnowledgeRetriever:
    """
    利用LLM选择需要加载的知识。
    """

    MAX_SELECTION = 3

    @classmethod
    def build_prompt(
            cls,
            query: str,
            knowledge: dict[str, KnowledgeItem],
    ) -> str:
        """
        构建知识选择Prompt。
        """

        sections = []

        for item in knowledge.values():

            line = (
                f"- {item.name}\n"
                f"  摘要：{item.summary}"
            )

            if item.tags:
                line += (
                    "\n"
                    f"  标签：{'、'.join(item.tags)}"
                )

            sections.append(line)

        sections = "\n\n".join(sections)

        return f"""你是一名知识检索器。

你的任务不是回答用户，而是从已有知识中选择回答问题所需的知识。

可选知识如下：

{sections}

规则：

1. 最多输出 {cls.MAX_SELECTION} 个知识名称。
2. 每行输出一个名称。
3. 只能输出知识名称。
4. 如果都不需要，请输出：

none

用户输入：

{query}
"""

    @staticmethod
    def parse_response(
            response: str,
            knowledge: dict[str, KnowledgeItem],
    ) -> dict[str, KnowledgeItem]:
        """
        解析LLM输出。
        """

        response = response.strip()

        if not response:
            return {}

        if response.lower() == "none":
            return {}

        result: dict[str, KnowledgeItem] = {}

        for line in response.splitlines():

            key = line.strip()

            if key in knowledge:
                result[key] = knowledge[key]

        print(f"[KnowledgeRetriever] 选择的知识条目有：{list(result.keys())}")
        return result


if __name__ == "__main__":
    knowledge = KnowledgeLoader.load("LuoTianyi")
    user_query = "洛天依什么时候发布的V5声库"
    selector_prompt = KnowledgeRetriever.build_prompt(
        query=user_query,
        knowledge=knowledge,
    )

    conv = ConversationManager(
        system_prompt=selector_prompt,
    )

    conv.add_user(user_query)
    llm = LLMDSAPI(
        model=LLMModelType.DS_FLASH,
    )
    reply = llm.one_chat(conv.messages)

    selected = KnowledgeRetriever.parse_response(
        reply,
        knowledge,
    )
    print("用户输入:", user_query)
    print("LLM 输出:", reply)
    print("选择的知识:", selected)

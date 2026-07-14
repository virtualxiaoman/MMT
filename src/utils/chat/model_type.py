from enum import Enum


class LLMModelType(Enum):
    """
    模型类型
    """

    DS_FLASH = "deepseek-v4-flash"  # 判别
    DS_PRO = "deepseek-v4-pro"  # 聊天
    QWEN_VL_PLUS = "qwen3-vl-plus"  # 识图

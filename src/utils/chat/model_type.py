from enum import Enum


class LLMModelType(Enum):
    """
    模型类型
    """

    DS_FLASH = "deepseek-v4-flash"
    DS_PRO = "deepseek-v4-pro"
    QWEN_VL_PLUS = "qwen3-vl-plus"

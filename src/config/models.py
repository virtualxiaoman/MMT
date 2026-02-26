import yaml
import os
from pathlib import Path

from src.config.path import CONFIG_DIR


class ModelConfig:
    # --- 严格的默认配置 ---
    DEFAULT_CONFIG = {
        "reply_model": {"name": "deepseek-chat", "type": "api"},
        "decide_model": {"name": "qwen3-vl:4b", "type": "local"},
        "emoji_model": {"name": "deepseek-chat", "type": "api"},
    }
    # 别名表，允许用户在配置文件中使用更简洁的名称，内部会自动转换为正式名称
    NAME_ALIASES = {
        "ds": "deepseek-chat",
        "deepseek": "deepseek-chat",
        "qwen": "qwen3-vl:4b",
        "qwen-4b": "qwen3-vl:4b",
        "qwen-8b": "qwen3-vl:8b",
        "qwen4b": "qwen3-vl:4b",
        "qwen8b": "qwen3-vl:8b",
    }

    # --- 模型+类型的组合 ---
    # 回复
    ALLOWED_REPLY_COMBOS = [
        ("deepseek-chat", "api"),
        # ("qwen3-vl:4b", "local"), # 假设未来回复模型也支持本地 qwen
    ]

    ALLOWED_DECIDE_COMBOS = [
        ("qwen3-vl:4b", "local"),
        ("qwen3-vl:8b", "local"),
        ("deepseek-chat", "api"),
    ]
    ALLOWED_EMOJI_COMBOS = [
        ("deepseek-chat", "api"),
    ]

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(CONFIG_DIR) / "models.yaml"
        self.config = self.DEFAULT_CONFIG.copy()
        self._load_and_validate(config_path)

    def _get_standard_name(self, name):
        """将别名转换为标准名称"""
        if not name or not isinstance(name, str):
            return name
        # 转小写后查表，如果查不到别名，则返回原名
        return self.NAME_ALIASES.get(name.lower(), name)

    def _load_and_validate(self, path):
        if not os.path.exists(path):
            print(f"ℹ️ 配置文件 {path} 未找到，将使用预设默认值。")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data or "models" not in data:
                    return

                m = data["models"]

                # --- 校验逻辑提取为内部函数 ---
                def validate_section(section_name, allowed_combos):
                    req = m.get(section_name, {})
                    raw_name = req.get("name")
                    model_type = req.get("type")

                    # 1. 别名转换
                    standard_name = self._get_standard_name(raw_name)

                    # 2. 组合校验
                    current_tuple = (standard_name, model_type)
                    if current_tuple in allowed_combos:
                        # 存储标准化的名称
                        self.config[section_name] = {"name": standard_name, "type": model_type}
                    else:
                        print(f"⚠️ {section_name} 配置无效: {current_tuple}，回滚至默认值。")

                # 执行校验
                validate_section("reply_model", self.ALLOWED_REPLY_COMBOS)
                validate_section("decide_model", self.ALLOWED_DECIDE_COMBOS)
                validate_section("emoji_model", self.ALLOWED_EMOJI_COMBOS)

        except Exception as e:
            print(f"❌ 解析配置文件失败: {e}")

    # --- 外部访问接口 ---
    @property
    def reply(self):
        return self.config["reply_model"]

    @property
    def decide(self):
        return self.config["decide_model"]

    @property
    def emoji(self):
        return self.config["emoji_model"]


# 全局单例，方便直接导入使用
model_settings = ModelConfig()

#
# def run_decision_logic():
#     # 自动获得经校验过的配置
#     decider = model_settings.decide
#     print(f"正在启动决策引擎: {decider['name']}，部署方式: {decider['type']}")
#     replier = model_settings.reply
#     print(f"正在启动回复引擎: {replier['name']}，部署方式: {replier['type']}")
#     # 这里可以根据 decider 和 replier 的配置来实例化对应的模型类，例如：
#     # if decider['name'] == "qwen3-vl:4b" and decider['type'] == "local":
#     #     my_decider = QwenDecider(model_size="4b", deploy_type="local")
#
#
# run_decision_logic()

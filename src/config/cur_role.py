from pathlib import Path
import yaml
import os

from src.config.path import CONFIG_DIR


class CurrentRole:
    def __init__(self):
        self.file_path = Path(CONFIG_DIR) / "current_role.yaml"
        self.role_name_zh = None
        self.role_name_en = None
        self.current_role = {}

    def update_role_yaml(self, role_name_zh, role_name_en):
        """
        将 self.role_name_zh 和 self.role_name_en 写入指定的 YAML 文件。
        如果文件不存在，则创建；如果存在，则更新其中的 role 字段。
        """
        self.role_name_zh = role_name_zh
        self.role_name_en = role_name_en
        # 准备要写入的数据
        new_data = {
            'role': {
                'name-zh': role_name_zh,
                'name-en': role_name_en
            }
        }

        # 如果文件已存在，读取原有内容，并更新 role 部分
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                try:
                    existing_data = yaml.safe_load(f) or {}
                except yaml.YAMLError:
                    existing_data = {}
        else:
            existing_data = {}

        # 合并数据：如果已有 role 键，则更新其子键；否则直接添加 role
        if 'role' in existing_data and isinstance(existing_data['role'], dict):
            existing_data['role'].update(new_data['role'])
        else:
            existing_data['role'] = new_data['role']

        # 写回文件（覆盖原文件）
        with open(self.file_path, 'w', encoding='utf-8') as f:
            yaml.dump(existing_data, f, allow_unicode=True, default_flow_style=False)

        print(f"已更新角色信息到 {self.file_path}，中文名：{self.role_name_zh}，英文名：{self.role_name_en}")

    def load_role_yaml(self):
        """
        从 YAML 文件加载角色信息，将顶层 role 下的键名中的连字符替换为下划线，
        存入 self.current_role。
        如果文件不存在或格式错误，current_role 置为空字典。
        """
        if not os.path.exists(self.file_path):
            self.current_role = {}
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError):
            self.current_role = {}
            return

        # 提取 role 部分，如果不存在则设为空字典
        role_data = data.get('role', {})
        if not isinstance(role_data, dict):
            role_data = {}

        # 将键名中的连字符替换为下划线，例如 name-zh -> name_zh
        converted = {}
        for key, value in role_data.items():
            new_key = key.replace('-', '_')
            converted[new_key] = value

        self.current_role = converted
        self.role_name_zh = self.current_role.get('name_zh')
        self.role_name_en = self.current_role.get('name_en')

    @property
    def name_zh(self):
        """返回角色的中文名称，如果不存在则返回 None"""
        self.load_role_yaml()
        return self.current_role.get('name_zh')

    @property
    def name_en(self):
        """返回角色的英文名称，如果不存在则返回 None"""
        self.load_role_yaml()
        return self.current_role.get('name_en')


# 全局单例，方便直接导入使用
current_role = CurrentRole()

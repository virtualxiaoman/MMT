import yaml
import os
import time
import logging
from pathlib import Path

from src.config.path import CONFIG_DIR

logger = logging.getLogger(__name__)


class QQReplyConfigReLoader:
    """配置文件管理器：支持热更新和别名解析"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(QQReplyConfigReLoader, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_path=Path(CONFIG_DIR) / "QQ_reply_settings.yaml"):
        if hasattr(self, "_initialized"):
            return  # 避免重复初始化
        self.config_path = config_path
        self._config = {}
        self._last_mtime = 0
        self._initialized = True
        self.reload()

    def reload(self):
        """检查文件是否有变动，如果有则重新加载"""
        try:
            current_mtime = os.path.getmtime(self.config_path)  # 获取当前文件的修改时间
            if current_mtime > self._last_mtime:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f)
                self._last_mtime = current_mtime
                print(f"[Config] 配置文件已热更新: {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[Config] 加载失败: {e}")

    def get_bot_config(self, bot_id: str):
        """获取指定机器人的配置，若无则返回 default"""
        self.reload()  # 每次获取时尝试检查更新
        bots = self._config.get("QQ", {})
        # 确保 bot_id 是字符串
        bot_id = str(bot_id)
        if bot_id in bots:
            # print(f"[Config] 获取到机器人 qq_id={bot_id}，名称是 {bots[bot_id].get('name', 'Error')} 的配置")
            return bots[bot_id]
        return bots.get("default", {})

    # ===== 读取公共配置 =====
    def get_common_parts(self):
        self.reload()
        return self._config.get("common_parts", {})


class QQReplySettings:
    """权限校验"""

    def __init__(self, bot_id: str | int):
        self.bot_id = str(bot_id)
        self.reply_settings = QQReplyConfigReLoader()

    def _check_access(self, conf: dict, target_id: int, super_whitelist: int | None = None) -> bool:
        """内部通用逻辑判断"""
        # ===== 管理员永远允许 =====
        if super_whitelist is not None and target_id == super_whitelist:
            logger.debug("[QQReplySettings] %s 是管理员对象，强制允许访问", target_id)
            return True

        mode = str(conf.get("mode", "auto")).lower()

        # 1. 强制开关判断
        if mode == "true":
            logger.debug("[QQReplySettings] %s 的 mode 设置为 true，强制允许访问", self.bot_id)
            return True
        elif mode == "false":
            logger.debug("[QQReplySettings] %s 的 mode 设置为 false，强制拒绝访问", self.bot_id)
            return False
        else:
            # 2. auto 模式：优先级 白名单 > 黑名单
            whitelist = conf.get("whitelist", [])
            blacklist = conf.get("blacklist", [])

            if target_id in whitelist:
                logger.debug("[QQReplySettings] %s 在 %s 的白名单中，允许访问", target_id, self.bot_id)
                return True
            if target_id in blacklist:
                logger.debug("[QQReplySettings] %s 在 %s 的黑名单中，拒绝访问", target_id, self.bot_id)
                return False

            # 3. 如果都不在，默认允许
            logger.debug("[QQReplySettings] %s 不在 %s 的白名单或黑名单中，默认允许访问", target_id, self.bot_id)
            return True

    @staticmethod
    def _to_int(value) -> int:
        """配置里的 ID 可能是 str/int/None，统一安全转 int，失败返回 -1。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    def can_reply_private(self, user_id: int) -> bool:
        """
        是否响应私聊
        :param user_id: 用户 QQ 号
        """
        bot_conf = self.reply_settings.get_bot_config(self.bot_id)
        private_conf = bot_conf.get("private", {})
        common_parts = self.reply_settings.get_common_parts()
        admin_qq = self._to_int(common_parts.get("admin_qq"))
        return self._check_access(conf=private_conf, target_id=user_id, super_whitelist=admin_qq)

    def can_reply_group(self, group_id: int, user_id: int | None = None) -> bool:
        """
        是否响应群聊
        :param group_id: 群号
        :param user_id: 发送者 QQ；用于在群级别放行后继续校验用户黑名单
        """
        bot_conf = self.reply_settings.get_bot_config(self.bot_id)
        group_conf = bot_conf.get("group", {})
        common_parts = self.reply_settings.get_common_parts()
        admin_qq = self._to_int(common_parts.get("admin_qq"))
        admin_group = self._to_int(common_parts.get("admin_group"))
        uid = self._to_int(user_id) if user_id is not None else None

        # 管理员私聊号永远放行；管理员群号也放行。
        if uid is not None and uid == admin_qq and admin_qq != -1:
            return True
        if self._to_int(group_id) == admin_group and admin_group != -1:
            return True

        mode = str(group_conf.get("mode", "auto")).lower()
        whitelist = group_conf.get("whitelist", [])
        blacklist = group_conf.get("blacklist", [])

        # 先执行黑名单（群黑名单、用户黑名单），再执行群白名单，确保封禁用户不会被群白名单放行。
        if group_id in blacklist:
            return False
        if uid is not None:
            user_blacklist = group_conf.get("user_blacklist", [])
            if uid in user_blacklist:
                return False
        if group_id in whitelist:
            return True

        if mode == "true":
            return True
        if mode == "false":
            return False
        return True

    def can_reply(self, session_id, is_private: bool, user_id: int | None = None) -> bool:
        """
        综合判断是否响应消息
        :param session_id: 用户 QQ 号（私聊）或 群号（群聊）
        :param is_private: 是否为私聊
        :param user_id: 群聊消息的发送者 QQ，私聊时可省略
        """
        if is_private:
            return self.can_reply_private(int(session_id))
        else:
            return self.can_reply_group(int(session_id), user_id=user_id)


# --- 使用示例 ---
if __name__ == "__main__":
    qq_reply_settings = QQReplySettings("1121221045")

    # 模拟收到私聊消息
    tester_id = 114514
    if qq_reply_settings.can_reply_private(tester_id):
        print(f"用户 {tester_id} 的私聊消息将被回复")
    else:
        print(f"用户 {tester_id} 的私聊消息将被忽略")

    # 模拟收到白子机器人的群聊
    shiroko_guard = QQReplySettings("1291606697")
    print(f"白子是否在群 1039857271 发言: {shiroko_guard.can_reply_group(1039857271)}")

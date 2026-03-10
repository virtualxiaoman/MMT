# """
# config_acl.py
#
# 使用说明：
#   loader = YamlBotConfig("path/to/config.yaml")
#   acl = QQReplySettings(loader)
#
#   # 同步查询
#   acl.can_reply(bot_id="1121221045", user_id=2958694743, is_group=False)
#
#   # 启动后台热更新（可选）
#   acl.start_auto_reload(poll_interval=1.0)
#
#   # 注册变更回调
#   def on_change(cfg):
#       print("config changed")
#   acl.register_callback(on_change)
# """
# from typing import Any, Dict, Optional, Set, Callable
# import threading
# import time
# import os
# import logging
# import yaml
# from pathlib import Path
#
# from src.config.path import CONFIG_DIR
#
# logger = logging.getLogger(__name__)
#
#
# def _to_int_set(value: Any) -> Set[int]:
#     """把 scalar/sequence/None 规范化为 int set"""
#     if value is None:
#         return set()
#     if isinstance(value, (int, str)):
#         try:
#             return {int(value)}
#         except ValueError:
#             return set()
#     result = set()
#     for v in value:
#         try:
#             result.add(int(v))
#         except Exception:
#             continue
#     return result
#
#
# class YamlBotConfig:
#     """
#     负责加载与解析 YAML 配置文件，并提供读取原始结构的接口。
#     - 不做复杂业务合并，保留原始节点；QQReplySettings 在业务层合并（更可控）。
#     """
#
#     def __init__(self, path: str):
#         self.path = path
#         self._lock = threading.RLock()
#         self._cfg: Dict[str, Any] = {}
#         self._mtime: float = 0.0
#         self.load()
#
#     def load(self) -> None:
#         """强制加载配置文件（首次或 reload）"""
#         with self._lock:
#             if not os.path.exists(self.path):
#                 raise FileNotFoundError(f"配置文件不存在: {self.path}")
#             mtime = os.path.getmtime(self.path)
#             with open(self.path, "r", encoding="utf-8") as f:
#                 raw = yaml.safe_load(f) or {}
#             # 记录
#             self._cfg = raw
#             self._mtime = mtime
#             logger.info("配置已加载: %s (mtime=%s)", self.path, mtime)
#
#     def reload_if_changed(self) -> bool:
#         """若文件 mtime 发生变化则 reload，返回是否发生了 reload"""
#         with self._lock:
#             if not os.path.exists(self.path):
#                 return False
#             mtime = os.path.getmtime(self.path)
#             if mtime != self._mtime:
#                 logger.info("配置文件变更检测到，重新加载: %s", self.path)
#                 self.load()
#                 return True
#             return False
#
#     def get_raw(self) -> Dict[str, Any]:
#         with self._lock:
#             # 返回浅拷贝，避免调用方误改
#             return dict(self._cfg)
#
#     # 下面是几个便捷查询方法
#     def get_common_parts(self) -> Dict[str, Any]:
#         raw = self.get_raw()
#         return raw.get("common_parts", {})
#
#     def get_bot_node(self, bot_id: str) -> Dict[str, Any]:
#         raw = self.get_raw()
#         qqs = raw.get("QQ", {}) or {}
#         node = qqs.get(str(bot_id))
#         if node is None:
#             node = qqs.get("default", {}) or {}
#         return node
#
#
# class QQReplySettings:
#     """
#     提供业务级别的访问判断与名单获取接口。
#     逻辑要点：
#       - admin_qq (common_parts.admin_qq) 永远强制允许（私聊与群聊均允许）。
#       - group 管理员(admin_group) 只是默认白名单，**可被 mode=false 屏蔽**（按您注释的需求）。
#       - mode: "true" | "false" | "auto"
#           - true: 总是允许（忽略名单）
#           - false: 总是拒绝（忽略名单）
#           - auto: 使用 whitelist/blacklist 决策。优先 whitelist（白名单优先于黑名单）。
#       - 若 bot 配置缺失，使用 "default" 节点（如存在）。
#     """
#
#     def __init__(self, loader: YamlBotConfig):
#         self.loader = loader
#         self._lock = threading.RLock()
#         self._callbacks: Set[Callable[[Dict[str, Any]], None]] = set()
#         self._reload_thread: Optional[threading.Thread] = None
#         self._reload_stop = threading.Event()
#
#     # ---- 名单读取/规范化 ----
#     def _common_admin_qq(self) -> Optional[int]:
#         common = self.loader.get_common_parts()
#         admin = common.get("admin_qq")
#         try:
#             return int(admin) if admin is not None else None
#         except Exception:
#             return None
#
#     def _common_admin_group(self) -> Optional[int]:
#         common = self.loader.get_common_parts()
#         grp = common.get("admin_group")
#         try:
#             return int(grp) if grp is not None else None
#         except Exception:
#             return None
#
#     def _get_lists_for_bot(self, bot_id: str, scope: str) -> Dict[str, Set[int]]:
#         """
#         scope in {"private", "group"}
#         返回结构：{"whitelist": set, "blacklist": set, "mode": str}
#         """
#         node = self.loader.get_bot_node(bot_id)
#         section = node.get(scope, {}) or {}
#         # mode 兼容 bool/string
#         mode = section.get("mode", section.get("model", "auto"))
#         if isinstance(mode, bool):
#             mode = "true" if mode else "false"
#         mode = str(mode).lower()
#
#         wl = _to_int_set(section.get("whitelist"))
#         bl = _to_int_set(section.get("blacklist"))
#         return {"whitelist": wl, "blacklist": bl, "mode": mode}
#
#     # ---- 对外接口 ----
#     def get_admins(self, bot_id: str) -> Dict[str, Optional[int]]:
#         """
#         返回 {'admin_qq': int|None, 'admin_group': int|None}
#         admin_qq 来自 common_parts.admin_qq（全局单一管理员）
#         admin_group 来自 common_parts.admin_group（群号）
#         """
#         return {
#             "admin_qq": self._common_admin_qq(),
#             "admin_group": self._common_admin_group(),
#         }
#
#     def get_whitelist(self, bot_id: str, scope: str = "private") -> Set[int]:
#         return self._get_lists_for_bot(bot_id, scope)["whitelist"]
#
#     def get_blacklist(self, bot_id: str, scope: str = "private") -> Set[int]:
#         return self._get_lists_for_bot(bot_id, scope)["blacklist"]
#
#     def can_reply(
#             self,
#             bot_id: str,
#             user_id: int,
#             is_group: bool = False,
#             group_id: Optional[int] = None,
#     ) -> bool:
#         """
#         核心判断函数：
#           - 若 user_id == admin_qq => 强制允许（符合您的注释“无论如何强制允许使用”）
#           - 否则按对应 scope (private/group) 的 mode/whitelist/blacklist 判定
#           - 对 group 判定时，如果 group_id 未提供，退化为 private 判定（调用方最好在群消息时传 group_id）
#         """
#         with self._lock:
#             admin_qq = self._common_admin_qq()
#             if admin_qq is not None and int(user_id) == int(admin_qq):
#                 return True  # 管理员永远允许
#
#             scope = "group" if is_group else "private"
#             lists = self._get_lists_for_bot(bot_id, scope)
#             wl = lists["whitelist"]
#             bl = lists["blacklist"]
#             mode = lists["mode"]
#
#             # 若是群消息但没有 group_id，则退化为私聊判定（保守）
#             if is_group and group_id is None:
#                 # 若没有群 id 无法判断群白/黑名单，退回到 private 行为
#                 scope = "private"
#                 lists = self._get_lists_for_bot(bot_id, "private")
#                 wl = lists["whitelist"]
#                 bl = lists["blacklist"]
#                 mode = lists["mode"]
#
#             # whitelist 优先
#             if user_id in wl:
#                 return True
#
#             # 对群消息，还应检查 group_id 是否在相关的群白/黑名单（如果群白名单存放的是群 id）
#             if is_group and group_id is not None:
#                 # 注意：配置里 group.whitelist/blacklist 可能存放群 id，而不是 user id
#                 # 若 group whitelist 存在且包含该群 id，则允许（群范围的优先级）
#                 if group_id in wl:
#                     return True
#                 if group_id in bl:
#                     return False
#
#             # 然后检查用户是否在黑名单
#             if user_id in bl:
#                 return False
#
#             # mode 处理
#             if mode == "true":
#                 return True
#             if mode == "false":
#                 return False
#
#             # auto 且既不在白名单也不在黑名单 -> 默认拒绝（更安全）
#             return False
#
#     # ---- 热更新支持 ----
#     def register_callback(self, fn: Callable[[Dict[str, Any]], None]) -> None:
#         """注册配置变更回调（函数接收 loader.get_raw()）"""
#         with self._lock:
#             self._callbacks.add(fn)
#
#     def unregister_callback(self, fn: Callable[[Dict[str, Any]], None]) -> None:
#         with self._lock:
#             self._callbacks.discard(fn)
#
#     def _fire_callbacks(self) -> None:
#         cfg = self.loader.get_raw()
#         for fn in list(self._callbacks):
#             try:
#                 fn(cfg)
#             except Exception:
#                 logger.exception("回调执行失败: %s", fn)
#
#     def start_auto_reload(self, poll_interval: float = 1.0) -> None:
#         """启动后台线程轮询文件变更并 reload（线程为 daemon）。"""
#         with self._lock:
#             if self._reload_thread and self._reload_thread.is_alive():
#                 return
#             self._reload_stop.clear()
#             t = threading.Thread(target=self._reload_loop, args=(poll_interval,), daemon=True)
#             self._reload_thread = t
#             t.start()
#             logger.info("已启动配置热更新线程 (interval=%s)", poll_interval)
#
#     def stop_auto_reload(self) -> None:
#         with self._lock:
#             if not self._reload_thread:
#                 return
#             self._reload_stop.set()
#             self._reload_thread.join(timeout=2.0)
#             self._reload_thread = None
#             logger.info("已停止配置热更新线程")
#
#     def _reload_loop(self, poll_interval: float) -> None:
#         while not self._reload_stop.is_set():
#             try:
#                 changed = self.loader.reload_if_changed()
#                 if changed:
#                     logger.info("配置已重新加载，触发回调")
#                     self._fire_callbacks()
#             except Exception:
#                 logger.exception("热更新轮询过程中发生异常")
#             time.sleep(poll_interval)
#
#
# if __name__ == "__main__":
#     cfg = YamlBotConfig(Path(CONFIG_DIR) / "QQ_reply_settings.yaml")
#     acl = QQReplySettings(cfg)
#
#     # 简单查询
#     print(acl.get_admins("1121221045"))
#     print(acl.get_whitelist("1121221045"))
#     print(acl.can_reply("1121221045", user_id=2958694743, is_group=False))
#
#     # 启动热更新（守护线程）
#     acl.start_auto_reload(poll_interval=2.0)
#
#
#     # 注册回调（当配置变更时，可在回调里触发热加载相关组件）
#     def cfg_changed(raw_cfg):
#         print("config changed")
#
#
#     acl.register_callback(cfg_changed)
#
import yaml
import os
import time
from pathlib import Path

from src.config.path import CONFIG_DIR


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


class QQReplySettings:
    """权限校验"""

    def __init__(self, bot_id: str | int):
        self.bot_id = str(bot_id)
        self.reply_settings = QQReplyConfigReLoader()

    def _check_access(self, conf: dict, target_id: int) -> bool:
        """内部通用逻辑判断"""
        mode = str(conf.get("mode", "auto")).lower()

        # 1. 强制开关判断
        if mode == "true":
            print(f"[QQReplySettings] {self.bot_id} 的 mode 设置为 true，强制允许访问")
            return True
        if mode == "false":
            print(f"[QQReplySettings] {self.bot_id} 的 mode 设置为 false，强制拒绝访问")
            return False

        # 2. auto 模式：优先级 白名单 > 黑名单
        whitelist = conf.get("whitelist", [])
        blacklist = conf.get("blacklist", [])

        if target_id in whitelist:
            print(f"[QQReplySettings] {target_id} 在 {self.bot_id} 的白名单中，允许访问")
            return True
        if target_id in blacklist:
            print(f"[QQReplySettings] {target_id} 在 {self.bot_id} 的黑名单中，拒绝访问")
            return False

        # 3. 如果都不在，默认允许
        print(f"[QQReplySettings] {target_id} 不在 {self.bot_id} 的白名单或黑名单中，默认允许访问")
        return True

    def can_reply_private(self, user_id: int) -> bool:
        """
        是否响应私聊
        :param user_id: 用户 QQ 号
        """
        bot_conf = self.reply_settings.get_bot_config(self.bot_id)
        private_conf = bot_conf.get("private", {})
        return self._check_access(private_conf, user_id)

    def can_reply_group(self, group_id: int) -> bool:
        """
        是否响应群聊
        :param group_id: 群号
        """
        bot_conf = self.reply_settings.get_bot_config(self.bot_id)
        group_conf = bot_conf.get("group", {})
        return self._check_access(group_conf, group_id)

    def can_reply(self, session_id, is_private: bool) -> bool:
        """
        综合判断是否响应消息
        :param session_id: 用户 QQ 号（私聊）或 群号（群聊）
        :param is_private: 是否为私聊
        """
        if is_private:
            return self.can_reply_private(int(session_id))
        else:
            return self.can_reply_group(int(session_id))


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

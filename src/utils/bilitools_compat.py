"""BiliTools 兼容钩子。

MMT 和 BiliTools 都以 ``src`` 作为顶层包名，而 BiliTools 内部全部使用绝对导入
（``from src.services import ...`` 等）。直接导入 ``libs.BiliTools.src`` 时，
``src`` 会被解析成 MMT 自己的包，导致 ``ModuleNotFoundError``。

本模块注册一个 ``sys.meta_path`` 查找器：导入 ``libs.BiliTools.src.*`` 时，
在内存中把模块源码里的 ``from src.`` / ``import src.`` 改写成
``from libs.BiliTools.src.`` / ``import libs.BiliTools.src.``，再编译执行。
所有 BiliTools 模块都挂在 ``libs.BiliTools.src.*`` 名字空间下，与 MMT 的 ``src``
完全隔离，BiliTools 磁盘文件零改动，submodule 更新也不受影响。

必须在第一次 ``from libs.BiliTools...`` 之前 import 本模块
（已在 QQBot 与 commands 顶部引入）。
"""

import importlib.abc
import importlib.util
import re
import sys
from pathlib import Path

# libs/BiliTools/src 相对本文件位置：MMT 根 / src / utils
BILI_SRC = Path(__file__).resolve().parents[2] / "libs" / "BiliTools" / "src"
if not (BILI_SRC / "__init__.py").is_file():
    raise RuntimeError(f"未找到 BiliTools 源码目录: {BILI_SRC}")

# BiliTools 模块在 MMT 内挂载的名字空间前缀
NS = "libs.BiliTools.src"

# 匹配行首（可带缩进）的 from src.x import y / import src.x
# 注意：行首空白必须捕获并在替换时保留，否则缩进会被吞掉；
# 且行首空白只能用 [ \t]*，不能用 \s*（MULTILINE 下 \s* 会跨行吞掉空行和缩进）
_REWRITE = re.compile(
    r"^(?P<indent>[ \t]*)(from|import)\s+src\.([a-zA-Z_]\w*(?:\.\w+)*)",
    re.MULTILINE,
)


class _BiliLoader(importlib.abc.Loader):
    """读取 BiliTools 源码文件，改写其中的 src.* 绝对导入后执行。"""

    def __init__(self, py_path: Path):
        self.py_path = py_path

    def exec_module(self, module):
        # 自定义加载器时导入系统不会自动设置 __file__，而 BiliTools 依赖它定位路径
        module.__file__ = str(self.py_path)
        code = self.py_path.read_text(encoding="utf-8")
        code = _REWRITE.sub(r"\g<indent>\2 " + NS + r".\3", code)
        exec(compile(code, str(self.py_path), "exec"), module.__dict__)


class _BiliFinder(importlib.abc.MetaPathFinder):
    """把 libs.BiliTools.src.* 解析到 libs/BiliTools/src 下的真实文件。"""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == NS:
            init = BILI_SRC / "__init__.py"
            spec = importlib.util.spec_from_loader(
                fullname, _BiliLoader(init), origin=str(init)
            )
            spec.submodule_search_locations = [str(BILI_SRC)]
            return spec
        if fullname.startswith(NS + "."):
            node = BILI_SRC / fullname[len(NS) + 1:].replace(".", "/")
            if node.is_dir():
                init = node / "__init__.py"
                if init.is_file():
                    spec = importlib.util.spec_from_loader(
                        fullname, _BiliLoader(init), origin=str(init)
                    )
                    spec.submodule_search_locations = [str(node)]
                    return spec
            else:
                py = node.with_suffix(".py")
                if py.is_file():
                    return importlib.util.spec_from_loader(
                        fullname, _BiliLoader(py), origin=str(py)
                    )
        return None


# 模块级代码每个进程只执行一次；插入到 PathFinder 之前，保证优先接管
sys.meta_path.insert(0, _BiliFinder())

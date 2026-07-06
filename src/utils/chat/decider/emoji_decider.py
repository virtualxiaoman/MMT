import re
from typing import Union
from pathlib import Path
import random

from collections import defaultdict

from src.config.path import PROMPT_DIR, EMOJI_DIR
from src.config.cur_role import current_role
from src.utils.tools.file import load_from_txt
from src.utils.chat.role_chat import ChatDSAPI


# todo 暂时懒得支持在yaml里面修改
class EmojiDecider(ChatDSAPI):
    """
    根据文本决定发送哪个表情。

    emoji_map:
    {
        "开心": [Path("开心.png"), Path("开心_1.png")],
        "赞": [Path("赞_1.png"), Path("赞_2.png")],
        ...
    }
    """

    # 支持的图片格式
    IMAGE_SUFFIXES = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp"
    }

    # AI看到的最长表情名称
    MAX_EMOJI_NAME_LEN = 20

    def __init__(self, model_name=None):
        super().__init__(model_name=model_name or "deepseek-chat")

        self.emoji_dir = Path(EMOJI_DIR) / current_role.name_en

        # 核心数据
        self.emoji_map = self._build_emoji_map()
        self.emoji_list = sorted(self.emoji_map.keys())

        self.system_prompt = None
        self.init_role("EmojiDecider")

    # ------------------------------------------------------------------
    # 构建 emoji_map
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        文件名规范化

        开心.png        -> 开心
        开心_1.png      -> 开心
        开心_23.gif     -> 开心
        """

        name = name.strip()
        # 如果包含多个标签，只保留第一个。例如：哭哭, 委屈 -> 哭哭
        name = re.split(r"\s*,\s*", name, maxsplit=1)[0]
        # 去掉最后的 _数字
        name = re.sub(r"_\d+$", "", name)
        # 合并多个空格
        name = re.sub(r"\s+", " ", name)

        return name

    def _is_valid_name(self, name: str) -> bool:
        """
        判断该名字是否适合作为AI决策标签
        """

        if not name:
            return False

        # 太长，大概率不是情绪
        if len(name) > self.MAX_EMOJI_NAME_LEN:
            return False

        # 含明显句子标点
        if re.search(r"[，。！？,.!?：:；;（）()【】\[\]<>《》]", name):
            return False

        return True

    def _build_emoji_map(self):
        """
        返回

        {
            "开心":[Path(...),Path(...)],
            "赞":[Path(...),Path(...)],
            ...
        }
        """

        if not self.emoji_dir.exists():
            print(f"表情目录不存在：{self.emoji_dir}")
            return {}

        emoji_map = defaultdict(list)

        for file in self.emoji_dir.rglob("*"):

            if not file.is_file():
                continue

            if file.suffix.lower() not in self.IMAGE_SUFFIXES:
                continue

            key = self._normalize_name(file.stem)

            if not self._is_valid_name(key):
                continue

            emoji_map[key].append(file)

        # 排序，保证稳定
        emoji_map = {
            k: sorted(v)
            for k, v in sorted(emoji_map.items())
        }

        print(f"共加载 {len(emoji_map)} 个表情标签。")
        # print(emoji_map)

        return emoji_map

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def init_role(self, role_name) -> bool:
        """初始化Prompt"""

        self.role_name = role_name

        path = Path(PROMPT_DIR) / "tools/EmojiDecider.txt"

        try:

            role_prompt = load_from_txt(path)

            emoji_str = ", ".join(self.emoji_list)

            role_prompt = role_prompt.replace(
                "[...]",
                f"[{emoji_str}]"
            )
            # print(role_prompt)

            self.system_prompt = {
                "role": "system",
                "content": role_prompt
            }

            self.msg = [self.system_prompt]

            return True

        except Exception as e:
            print(f"初始化 EmojiDecider 失败: {e}")
            return False

    # ------------------------------------------------------------------
    # AI决策
    # ------------------------------------------------------------------

    def decide(self, text: str) -> Union[str, bool]:

        temp_msg = [
            self.system_prompt,
            {
                "role": "user",
                "content": text
            }
        ]

        try:

            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=temp_msg,
                temperature=0.0,
                stream=False
            )

            result = completion.choices[0].message.content.strip()

            if result in self.emoji_map:
                return result

            if result == "False":
                return False

            return False

        except Exception as e:
            print(f"表情决策请求异常: {e}")
            return False

    def one_chat(self, query: str) -> str:
        return str(self.decide(query))

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def get_emoji_path(self, text: str, p: float = 0.5):
        """
        根据文本返回表情路径。

        返回：
            str   图片路径
            False 无可用表情
        """

        if random.random() > p:
            return False

        emotion = self.decide(text)
        if not emotion:
            return False

        # 防止 AI 返回非法 key
        emoji_paths = self.emoji_map.get(emotion)
        if not emoji_paths:
            print(f"未知表情标签：{emotion}")
            return False

        # 过滤已经不存在的图片
        valid_paths = [path for path in emoji_paths if path.exists()]

        if not valid_paths:
            print(f"表情 '{emotion}' 的图片全部不存在。")
            return False

        return str(random.choice(valid_paths))


if __name__ == "__main__":
    # 实例化
    decider = EmojiDecider()

    # 测试用例
    texts = ["哇，这真是太不可思议了！", "今天天气真不错。", "我感觉有点不舒服...", "你这是在干嘛？！",
             "为什么要说这么坏心眼的话？"]

    for t in texts:
        emoji = decider.decide(t)
        if emoji:
            print(f"文本: {t} => 表情: [{emoji}]")
        else:
            print(f"文本: {t} => 无法匹配表情")

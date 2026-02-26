from typing import Union
from pathlib import Path
import random

from src.config.path import PROMPT_DIR, EMOJI_DIR
from src.utils.file import load_from_txt
from src.config.models import model_settings
from src.utils.chat import ChatDSAPI


class EmojiDecider(ChatDSAPI):
    def __init__(self, emoji_list=None, model_name=None):
        super().__init__(model_name=model_name or "deepseek-chat")
        if emoji_list is None:
            self.emoji_list = ["安详", "担忧", "好奇", "紧张", "惊讶", "难过", "平静", "微笑",
                               "委屈", "疑惑", "震惊"]  # 暂时只写白子的
        else:
            self.emoji_list = emoji_list
        self.system_prompt = None
        self.init_role("EmojiDecider")

    def init_role(self, role_name) -> bool:
        """重写初始化逻辑，专为表情决策设计"""
        self.role_name = role_name
        path = Path(PROMPT_DIR) / "tools/EmojiDecider.txt"
        try:
            role_prompt = load_from_txt(path)
            emoji_str = ", ".join(self.emoji_list)
            role_prompt = role_prompt.replace("[...]", f"[{emoji_str}]")  # 将提示词里面的 [...] 替换为实际的表情列表
            self.system_prompt = {
                "role": "system",
                "content": role_prompt
            }
            # print(f"初始化角色{role_name}的prompt成功，系统提示词已设置为:\n{self.system_prompt['content']}")
            self.msg = [self.system_prompt]
            return True
        except Exception as e:
            print(f"初始化 EmojiDecider 失败: {e}")
            return False

    def decide(self, text: str) -> Union[str, bool]:
        """
        核心方法：传入文本，返回表情词或 False
        """
        # 1. 构造无记忆的临时消息列表（只包含系统提示词和当前查询）
        temp_msg = [
            self.system_prompt,
            {
                "role": "user",
                "content": text
            }
        ]
        # print(self.system_prompt)
        # print(temp_msg)

        try:
            # 2. 调用 DeepSeek API
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=temp_msg,
                temperature=0.0,  # 决策任务建议将随机性降为 0
                stream=False
            )

            result = completion.choices[0].message.content.strip()

            # 3. 校验返回结果
            if result in self.emoji_list:
                return result
            elif "False" in result or result == "无":
                return False
            else:
                # 如果模型输出了列表外的词，也视为无效
                return False

        except Exception as e:
            print(f"表情决策请求异常: {e}")
            return False

    def one_chat(self, query: str) -> str:
        """重写父类方法，防止混淆使用"""
        res = self.decide(query)
        return str(res)

    def get_emoji_path(self, text, p=0.8):
        """提供一个外部接口，直接返回表情路径或 False"""
        if random.random() < p:  # 以 p 的概率调用模型决策，保持一定的随机性，避免过于死板
            res = self.decide(text)
            if res and res in self.emoji_list:
                print(f"表情: {res}")
                emoji_path = Path(EMOJI_DIR) / "Shiroko" / f"{res}.png"  # todo 这里应该使用self.role_name
                # 检查路径下是否存在对应的表情图片，如果不存在则返回 False
                if emoji_path.exists():
                    return str(emoji_path)
                else:
                    print(f"表情图片 {emoji_path} 不存在，无法返回表情路径。")
                    return False
        return False


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

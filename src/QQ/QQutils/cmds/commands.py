import logging
import random
import re
from datetime import datetime
from pathlib import Path
from base64 import b64decode
from typing import Literal

from openai import OpenAI

from src.QQ.QQutils.msg.msg_wrapper import RecvMessageWrapper
# todo 帮助只实现了洛天依的部分，可以考虑单独写一个类来自定义
from src.QQ.QQutils.msg.chat_session import MessageContext
from src.config.QQ_bot_info_loader import BotConfig
from src.config.path import PICTURES_DIR, HISTORY_DIR, PROMPT_DIR, QQ_HISTORY_DIR, VOICE_DIR, API_KEY_DIR
from src.utils.chat.history.manage_summary import SummaryManager, SummaryGenerator
from src.utils.chat.llm.run_prompt import PromptRunner
from src.utils.chat.role_chat import DeepSeekClient
from src.utils.tools.file import load_from_txt
from src.utils.tools.res.specify_lyric import LyricRepository
from src.utils.tools.res.specify_music import MusicRepository

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BaseCommand:
    def match(self, text: str) -> bool:
        raise NotImplementedError

    async def handle(self, ctx: MessageContext) -> bool:
        raise NotImplementedError


class CommandRegistry:
    def __init__(self):
        self.commands: list[BaseCommand] = []

    def register(self, cmd: BaseCommand):
        self.commands.append(cmd)

    async def dispatch(self, ctx) -> bool:
        for cmd in self.commands:
            if not cmd.match(ctx.tool_text):
                continue  # 不匹配
            handled = await cmd.handle(ctx)  # 是否成功处理
            if handled:
                return True
        return False
    # async def dispatch(self, ctx: MessageContext) -> bool:
    #     for cmd in self.commands:
    #         # print(ctx.user_raw_text)
    #         if cmd.match(ctx.user_raw_text):
    #             return await cmd.handle(ctx)  # 此逻辑有问题，因为歌词匹配是永远设置为True的
    #     return False


# --- 指令1：一图 ---可以以一图开始，比如指令“一图 -n 5”表示发5张图，默认发1张
class ImageCommand(BaseCommand):
    def match(self, text: str) -> bool:
        return text == "一图" or text.startswith("一图 ")

    # todo 没写非文本匹配的tool调用，例如@洛天依 来几张天依美图
    async def handle(self, ctx: MessageContext) -> bool:
        user_text = ctx.tool_text
        pic_nums = 1  # default
        # 解析指令参数，目前仅支持“-n 数字”来指定图片数量，默认1张
        if user_text.startswith("一图 "):
            parts = user_text.split()
            if len(parts) >= 3 and parts[1] == "-n" and parts[2].isdigit():
                pic_nums = max(1, min(int(parts[2]), 3))

        for i in range(pic_nums):
            path = ctx.session.random_picture_provider.get_random_image_path()
            if i == 0:
                await ctx.msg_sender.text(f"呐呐呐~coins-{5 * pic_nums}")  # 首次发文本提示扣除金币，后续只发图
                # todo 实际扣除金币逻辑
            await ctx.msg_sender.image(path)  # 发送图片

        return True


# --- 指令2：唱歌 ---
class MusicCommand(BaseCommand):
    def __init__(self, music_dir: str | list):
        self.music_dir = music_dir

    def match(self, text: str) -> bool:
        return text.startswith("唱") and len(text) > 1

    async def handle(self, ctx: MessageContext) -> bool:
        query = ctx.tool_text[1:].strip()
        send_record = True  # 默认发送语音
        send_file = False  # 默认不发送文件

        if query.endswith("-a"):
            send_record = True
            send_file = True
            query = query[:-2].strip()
        elif query.endswith("-f"):
            send_record = False
            send_file = True
            query = query[:-2].strip()

        if not query:
            await ctx.msg_sender.text("你想让天依唱什么呢？")
            return True

        keywords = re.split(r"[,+\s]+", query)
        keywords = [k.strip() for k in keywords if k.strip()]
        keywords = list(dict.fromkeys(keywords))

        music_finder = MusicRepository(song_names=keywords, music_dirs=self.music_dir)
        record_path = music_finder.find_music_by_name()
        if record_path:
            record_path = Path(record_path)
            if not record_path.is_file():
                logger.error(f"音乐文件不存在: {record_path}")
                record_path = None
        logger.info(f"歌曲关键词: {keywords}，音乐文件路径: {record_path}，发送语音={send_record}，发送文件={send_file}")

        if record_path:
            if send_record:
                await ctx.msg_sender.record(str(record_path))
            if send_file:
                await ctx.msg_sender.file(str(record_path), name=record_path.name)
        else:
            await ctx.msg_sender.text(f"抱歉，天依还不会唱《{' '.join(keywords)}》这首歌呢~你可以教教天依吗(>_<)")
            logger.warning(f"未找到匹配歌曲: {keywords}")
        return True

    # async def _find_music_file(self, song_name: str) -> str | None:
    #     """
    #     在指定目录下搜索包含 song_name 的音频文件
    #     """
    #     extensions = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac'}  # 支持的音频文件扩展名
    #     music_dir = Path(MUSIC_DIR)
    #
    #     # 如果目录不存在，直接返回 None
    #     if not music_dir.exists():
    #         logger.error(f"音乐目录不存在: {music_dir}")
    #         return None
    #
    #     # 遍历目录下所有文件
    #     for file in music_dir.rglob("*"):
    #         # file.is_file() 确保它是文件而不是文件夹
    #         # song_name.lower() in file.name.lower() 实现不区分大小写的包含匹配
    #         if file.is_file() and file.suffix.lower() in extensions:
    #             if song_name.lower() in file.name.lower():
    #                 # print(f"找到匹配的音乐文件: '{file.name}'，路径: {file.absolute()}")
    #                 return str(file.absolute())  # 返回绝对路径的字符串形式
    #
    #     return None


# --- 指令3：帮助 ---
class HelpCommand(BaseCommand):
    def match(self, text: str) -> bool:
        return text.lower() in ["help", "帮助", "菜单", "功能"]

    async def handle(self, ctx: MessageContext) -> bool:
        #       help_text = """꧁ 华风夏韵，洛水天依 ꧂
        # ♾️ 这里是天依，请多指教ෆ8( ˶'ᵕ'˶)ෆ
        # 🎨 图片小惊喜：
        #   -> 发送「一图」 → 天依会送你一张可爱的图片哦~ 如果想看更多，试试「一图 -n 2」，可以一次看到两张呢~
        # 🎤 为了你唱下去：
        #   -> 发送「唱+歌名」 → 天依来为你唱这首歌（比如：唱为了你唱下去）
        # 📋 小说明：
        #   -> 私聊的话，天依一定会好好地回应你哟(♡>𖥦<)/♡ 群聊里除了这些特别的指令，天依还在努力学习，希望能更好地陪着你(◔◡◔)
        #   -> 如果遇到什么问题，可以找我的好朋友virtual小满，她会帮你哒(⑅˃◡˂⑅)
        # ❤️ （轻轻歪头，眼里闪着温暖的光）诶嘿~天依虽然是纸片人，但通过歌声和大家的爱，真的能变得更有温度呢！天依会一直一直在这里，陪着你，唱歌给大家听的(๑>؂<๑）"""
        #       await ctx.msg_sender.text(help_text)
        help_path = PICTURES_DIR / "LuoTianyi/help.png"
        help_path = str(help_path.resolve())
        await ctx.msg_sender.image(help_path)
        return True


# --- 指令4：群打卡/签到 ---
class CheckinCommand(BaseCommand):
    def match(self, text: str) -> bool:
        return text == "打卡"

    async def handle(self, ctx: MessageContext) -> bool:

        if ctx.is_private:
            return False  # todo: 后续支持私聊指定某群的打卡

        try:
            await ctx.bot.api.set_group_sign(
                group_id=ctx.msg.group_id
            )
            await ctx.msg_sender.text("群签到完成~")
            logger.info(f"已完成群 {ctx.msg.group_id} 的签到")
        except Exception as e:
            logger.error(f"群签到失败: {e}")
            await ctx.msg_sender.text(f"签到失败了呢...")

        return True


# --- 指令5：接歌词 ---
class LyricCommand(BaseCommand):
    def __init__(self, lyric_dir: str | list):
        self.repository = LyricRepository(lyric_dir)

    def match(self, text: str) -> bool:
        return True

    async def handle(self, ctx: MessageContext) -> bool:
        result = self.repository.find_next_line(ctx.tool_text)
        if result is None:
            return False
        await ctx.msg_sender.text(result)
        return True


# --- 指令6：日报 ---
class DailyReportCommand(BaseCommand):

    def match(self, text: str) -> bool:
        # print(text)
        # return text == "日报"
        return text in ["日报", "每日日报", "每日聊天报告", "聊天报告"]

    async def handle(self, ctx: MessageContext) -> bool:
        generator = DailyReportGenerator(
            config=ctx.config,
            recv_msg_wrapper=ctx.recv_msg_wrapper
        )

        report = await generator.generate()

        await ctx.msg_sender.text(report)

        return True


class DailyReportGenerator:
    """
    每日日报生成器
    """

    def __init__(
            self,
            config: BotConfig,
            recv_msg_wrapper: RecvMessageWrapper
    ):
        self.config = config
        self.recv_msg_wrapper = recv_msg_wrapper

        self.bot_root = (
                Path(QQ_HISTORY_DIR)
                / str(config.bot_id)
        )

        self.client = DeepSeekClient()

        prompt_path = Path(PROMPT_DIR) / "tools/DailyReportGenerator.txt"

        self.system_prompt = load_from_txt(prompt_path)

    @property
    def llm_input_path(self) -> str:
        """
        获取今天对应会话的 llm_input 文件路径
        """

        session_type = (
            "private"
            if self.recv_msg_wrapper.is_private
            else "group"
        )

        now = datetime.now()

        month = now.strftime("%Y-%m")
        day = now.strftime("%Y-%m-%d")

        return str((
                           self.bot_root
                           / session_type
                           / str(self.recv_msg_wrapper.session_id)
                           / "llm_input"
                           / month
                           / f"{day}.txt"
                   ).resolve())

    def read_chat_history(self) -> str:
        """
        读取今天聊天记录
        """
        return load_from_txt(self.llm_input_path)

    # async def generate(self) -> str:
    #     """
    #     生成每日日报
    #     """
    #
    #     history = self.read_chat_history()
    #     # print(history)
    #
    #     if not history:
    #         return "今天还没有聊天记录。"

    #
    #     return "开发中"

    async def generate(
            self,
    ) -> str:
        chat_content = self.read_chat_history()
        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            },
            {
                "role": "user",
                "content": chat_content
            }
        ]

        return self.client.one_chat(
            messages,
            temperature=0.4
        )

        # todo 后续：工具化（代码）总结数据内容，图表，图片输出


# --- 指令7：禁言 ---
class BanCommand(BaseCommand):
    """
    #禁言 @123456 3分钟
    #解除禁言 @123456
    """

    # 单位 -> 秒
    TIME_UNITS = {
        "秒": 1,
        "分钟": 60,
        "分": 60,
        "小时": 3600,
        "时": 3600,
        "天": 86400,
    }

    def match(self, text: str) -> bool:
        text = text.strip()
        return text.startswith("#禁言") or text.startswith("#解除禁言")

    async def handle(self, ctx: MessageContext) -> bool:
        if str(ctx.recv_msg_wrapper.user_id) != str(ctx.config.admin_qq_id):
            await ctx.msg_sender.text("天依是为大家带来幸福的歌者，不是用来禁言别人的工具哦。"
                                      "只有我特别的伙伴小满才可以命令天依哒~")
            return True
        text = ctx.tool_text

        # 必须在群聊
        if ctx.is_private:
            await ctx.msg_sender.text("只有群聊才能使用该命令。")
            return True

        # ----------------------------
        # 解除禁言
        # ----------------------------
        if text.startswith("#解除禁言"):
            m = re.search(r"@(\d+)", text)

            if not m:
                await ctx.msg_sender.text("格式错误：#解除禁言 @QQ号")
                return True

            user_id = int(m.group(1))

            await ctx.bot.api.set_group_ban(
                group_id=ctx.msg.group_id,
                user_id=user_id,
                duration=0,
            )

            await ctx.msg_sender.text("已解除禁言。")
            return True

        # ----------------------------
        # 禁言
        # ----------------------------
        m = re.search(
            r"#禁言\s*@(\d+)(?:\s+(\d+)\s*(秒|分钟|分|小时|时|天))?",
            text,
        )

        if not m:
            await ctx.msg_sender.text(
                "格式错误：#禁言 @QQ号 3分钟"
            )
            return True

        user_id = int(m.group(1))

        # 默认1分钟
        duration = 60

        if m.group(2):
            value = int(m.group(2))
            unit = m.group(3)

            duration = value * self.TIME_UNITS[unit]

        await ctx.bot.api.set_group_ban(
            group_id=ctx.msg.group_id,
            user_id=user_id,
            duration=duration,
        )

        await ctx.msg_sender.text(f"已禁言用户 {user_id} 共 {duration} 秒。")
        return True


# --- 指令8：早安 ---
class MorningCommand(BaseCommand):
    def __init__(self):
        pass

    def match(self, text: str) -> bool:
        return text in ["早安", "早上好", "早呀", "早上好呀", "早"]

    async def handle(self, ctx: MessageContext) -> bool:
        record_path_1 = VOICE_DIR / "LuoTianyi/大笨蛋，现在好像不是很早了呢.mp3"
        record_path_2 = VOICE_DIR / "LuoTianyi/您刚醒呢，都几点了这，还说早呢.mp3"  # todo: 支持更多语音
        record_paths = [str(record_path_1.resolve()), str(record_path_2.resolve())]
        record_path = random.choice(record_paths)
        # record_path = await self._find_music_file(song_name)
        logger.info(f"文件路径是: {record_path}")
        if record_path:
            await ctx.msg_sender.record(record_path)
        else:
            await ctx.msg_sender.text(f"天依还没起床呢")
            logger.warning(f"未找到匹配的早安文件: '{record_path}'")

        return True


class ImageGenerator:
    """
    AI图片生成器

    负责:
        - 调用图片生成API
        - 保存图片

    不负责:
        - 文件组织
        - QQ消息处理
    """

    def __init__(
            self,
            api_key: str | None = None,
            base_url: str = "https://yunwu.ai/v1",
            model: str = "gpt-image-2",
    ):
        if api_key is None:
            api_key = load_from_txt(
                Path(API_KEY_DIR) / "yunwu.txt"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        self.model = model

    def generate(
            self,
            prompt: str,
            save_path: str | Path,
            size: str = "1024x1024",
            quality: str = "high",
    ) -> Path:
        """
        生成图片

        Args:
            prompt:
                图片描述

            save_path:
                保存路径

        """

        response = self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )

        image_base64 = response.data[0].b64_json

        image = b64decode(image_base64)

        save_path = Path(save_path)

        save_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        save_path.write_bytes(image)

        return save_path


QualityType = Literal[
    "standard",
    "hd",
    "low",
    "medium",
    "high",
    "auto",
]


# --- 指令9：生成图片 ---
class ImageGeneratorCommand(BaseCommand):

    def __init__(self, config: BotConfig):
        self.bot_root = Path(QQ_HISTORY_DIR) / str(config.bot_id)
        self.generator = ImageGenerator()

    def match(self, text: str) -> bool:
        return text.startswith("#绘图")

    @staticmethod
    def _parse_args(text: str) -> tuple[str, QualityType]:
        """
        解析绘图参数。

        示例：

            天依睡觉
                -> ("天依睡觉", "auto")

            天依睡觉 -quality=high
                -> ("天依睡觉", "high")
        """

        quality: QualityType = "auto"

        match = re.search(r"-quality=(\w+)", text)

        if match:
            value = match.group(1).lower()

            if value in (
                    "standard",
                    "hd",
                    "low",
                    "medium",
                    "high",
                    "auto",
            ):
                quality = value

        # 去掉参数
        prompt = re.sub(
            r"\s*-quality=\w+",
            "",
            text,
        ).strip()

        return prompt, quality

    def _get_save_path(
            self,
            ctx: MessageContext,
            suffix: str = "png",
    ) -> Path:
        """
        生成图片保存路径

        bot_root/
            private or group/
                session_id/
                    AI_draw/
                        month/
                            day_i.png
        """

        now = datetime.now()

        month = now.strftime("%Y-%m")
        day = now.strftime("%Y-%m-%d")

        session_type = (
            "private"
            if ctx.recv_msg_wrapper.is_private
            else "group"
        )

        save_dir = (
                self.bot_root
                / session_type
                / str(ctx.session_id)
                / "AI_draw"
                / month
        )

        save_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        i = 1

        while True:

            path = save_dir / f"{day}_{i}.{suffix}"

            if not path.exists():
                return path

            i += 1

    async def handle(
            self,
            ctx: MessageContext,
    ) -> bool:

        text = ctx.recv_msg_wrapper.tool_msg

        # 去掉 "#绘图"
        text = text.replace(
            "#绘图",
            "",
            1,
        ).strip()

        prompt, quality = self._parse_args(text)

        if not prompt:
            await ctx.msg_sender.text(
                "提示词错误，请联系小满"
            )

            return True

        logger.info(
            f"AI绘图请求: prompt={prompt}, quality={quality}"
        )

        await ctx.msg_sender.text(
            f"正在绘制图片：{prompt}，大约需要30秒噢~"
        )

        try:

            save_path = self._get_save_path(ctx)

            image_path = self.generator.generate(
                prompt=prompt,
                save_path=save_path,
                quality=quality,
            )

            logger.info(
                f"AI图片生成完成: {image_path}"
            )

            await ctx.msg_sender.image(
                str(image_path)
            )

        except Exception as e:

            logger.exception(
                "AI绘图失败"
            )

            await ctx.msg_sender.text(
                f"绘图失败了呜... {e}"
            )

        return True


# --- 指令10：更新记忆 ---
class UpdateMemoryCommand(BaseCommand):
    """
    更新记忆
    """

    def match(self, text: str) -> bool:
        text = text.strip()
        return text in ["#更新记忆", "# 更新记忆"]

    async def handle(self, ctx: MessageContext) -> bool:
        if str(ctx.recv_msg_wrapper.user_id) != str(ctx.config.admin_qq_id):
            await ctx.msg_sender.text("记忆对天依来说是很珍贵的东西，不能随便让人碰的。"
                                      "只有我特别的伙伴小满才可以命令天依哒~")
            return True
        else:
            await ctx.msg_sender.text("天依正在了解大家的爱好，请耐心等待w")
        runner = PromptRunner()
        generator = SummaryGenerator(runner)
        manager = SummaryManager(
            bot_id=ctx.config.bot_id,
            is_private=ctx.is_private,
            session_id=ctx.session_id,
            generator=generator,
        )
        manager.update_long_term()
        manager.update_short_term()

        return True


if __name__ == "__main__":
    img_generator = ImageGenerator()
    path = img_generator.generate(
        prompt="画一张洛天依",
        save_path="../assets/pictures/AI_draw/test.png"
    )
    print(f"图片保存成功: {path}")

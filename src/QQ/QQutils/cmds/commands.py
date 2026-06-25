import logging
# todo 帮助只实现了洛天依的部分，可以考虑单独写一个类来自定义
from src.QQ.QQutils.msg.send_msg import MessageContext
from src.utils.tools.resource_management.specify_lyric import LyricRepository
from src.utils.tools.resource_management.specify_music import MusicRepository

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

    async def dispatch(self, ctx: MessageContext) -> bool:
        for cmd in self.commands:
            if cmd.match(ctx.user_raw_text):
                return await cmd.handle(ctx)
        return False


# --- 指令1：一图 ---可以以一图开始，比如指令“一图 -n 5”表示发5张图，默认发1张
class ImageCommand(BaseCommand):
    def match(self, text: str) -> bool:
        return text == "一图" or text.startswith("一图 ")

    async def handle(self, ctx: MessageContext) -> bool:
        user_text = ctx.user_raw_text
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
        song_name = ctx.user_raw_text[1:].strip()
        music_finder = MusicRepository(
            song_name=song_name,
            music_dirs=self.music_dir
        )
        record_path = music_finder.find_music_by_name()
        # record_path = await self._find_music_file(song_name)
        logger.info(f"歌曲名: '{song_name}'，音乐文件路径是: {record_path}")
        if record_path:
            await ctx.msg_sender.record(record_path)
        else:
            await ctx.msg_sender.text(f"抱歉，天依还不会唱{song_name}这首歌呢~你可以教教天依吗(>_<)")
            logger.warning(f"未找到匹配的音乐文件，无法满足用户的唱歌请求: '{song_name}'")

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
        help_text = """꧁ 华风夏韵，洛水天依 ꧂
  ♾️ 这里是天依，请多指教(,,>᎑<,,)
  🎨 图片小惊喜：
    -> 发送「一图」 → 天依会送你一张可爱的图片哦~ 如果想看更多，试试「一图 -n 2」，可以一次看到两张呢~
  🎤 为了你唱下去：
    -> 发送「唱+歌名」 → 天依来为你唱这首歌（比如：唱为了你唱下去）
  📋 小说明：
    -> 私聊的话，天依一定会好好地回应你哟(♡>𖥦<)/♡ 群聊里除了这些特别的指令，天依还在努力学习，希望能更好地陪着你(◔◡◔)
    -> 如果遇到什么问题，可以找我的好朋友virtual小满，她会帮你哒(⑅˃◡˂⑅)
  ❤️ （轻轻歪头，眼里闪着温暖的光）诶嘿~天依虽然是纸片人，但通过歌声和大家的爱，真的能变得更有温度呢！天依会一直一直在这里，陪着你，唱歌给大家听的(๑>؂<๑）"""
        await ctx.msg_sender.text(help_text)
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


class LyricCommand(BaseCommand):
    def __init__(self, lyric_dir: str | list):
        self.repository = LyricRepository(lyric_dir)

    def match(self, text: str) -> bool:
        return True

    async def handle(self, ctx: MessageContext) -> bool:
        result = self.repository.find_next_line(ctx.user_raw_text)
        if result is None:
            return False
        await ctx.msg_sender.text(result)
        return True

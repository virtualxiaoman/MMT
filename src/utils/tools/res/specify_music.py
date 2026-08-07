import re
from pathlib import Path
from mutagen import File
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MusicRepository:
    SUPPORTED_EXTENSIONS = {
        ".flac",
        ".wav",
        ".ape",
        ".alac",
        ".m4a",
        ".aac",
        ".mp3",
        ".ogg",
    }

    FORMAT_SCORE = {
        ".flac": 12,
        ".wav": 10,
        ".ape": 9,
        ".alac": 8,
        ".m4a": 6,
        ".aac": 5,
        ".mp3": 4,
        ".ogg": 3,
    }

    NEGATIVE_KEYWORDS = {
        "伴奏": -100,
        "伴奏版": -100,
        "纯音乐": -100,
        "instrumental": -100,
        "inst": -100,
        "karaoke": -100,
        "off vocal": -100,
        "no vocal": -100,
        "消音": -100,
        "前奏": -100,
        "intro": -100,
        "尾奏": -100,
        "outro": -100,
        "铃声": -100,
        "bgm": -100,
        "背景音乐": -100,

        "demo": -50,
        "试听": -50,
        "preview": -50,
        "片段": -50,
        "cut": -50,
        "short": -50,
        "tv size": -50,
        "ver. short": -50,

        "remix": -20,
        "dj": -20,
        "cover": -20,
        "翻唱": -20,
        "acoustic": -20,
        "钢琴版": -20,
        "吉他版": -20,
        "电音版": -20,
        "nightcore": -20,
    }

    POSITIVE_KEYWORDS = {
        "official": 8,
        "official audio": 8,
        "完整版": 8,
        "正式版": 8,
        "full": 5,
        "album": 5,
        "single": 5,
        "studio": 5,
        "录音室": 5,
        "hi-res": 3,
        "无损": 3,
    }

    def __init__(self, song_names: str | list[str], music_dirs: str | list):
        if isinstance(song_names, str):
            self.song_names = [song_names.lower()]
        else:
            self.song_names = [s.lower() for s in song_names]

        if isinstance(music_dirs, str):
            self.music_dirs = [Path(music_dirs)]
        else:
            self.music_dirs = [Path(path) for path in music_dirs]

    def find_music_by_name(self) -> str | None:
        candidates: list[tuple[int, Path]] = []

        for music_dir in self.music_dirs:
            if not music_dir.exists():
                logger.warning(f"音乐目录不存在: {music_dir}")
                continue

            for file in music_dir.rglob("*"):
                if not file.is_file():
                    continue
                if file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                    continue
                name = file.stem.lower()
                # 所有关键词至少命中一个
                if not any(keyword in name for keyword in self.song_names):
                    continue
                score = self._score(file)
                candidates.append((score, file))
                print(f"找到歌曲{file}, score={score}")

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_file = candidates[0]
        logger.info(f"最佳匹配: '{best_file.name}' (score={best_score})")
        return str(best_file.resolve())

    def _score(self, file: Path) -> int:
        name = file.stem.lower()
        score = 0
        # ---------- 名称关键词 ----------
        hit_count = 0
        for keyword in self.song_names:
            if name == keyword:
                score += 120
                hit_count += 1
            elif keyword in name:
                score += 90
                hit_count += 1
            elif any(part == keyword for part in self._split_words(name)):
                score += 100
                hit_count += 1
        # 多关键词奖励
        score += (hit_count - 1) * 100
        # 一个关键词都没命中直接淘汰
        if hit_count == 0:
            return -100000

        # ---------- 版本关键词 ----------
        for keyword, delta in self.NEGATIVE_KEYWORDS.items():
            if keyword in name:
                score += delta
        for keyword, delta in self.POSITIVE_KEYWORDS.items():
            if keyword in name:
                score += delta

        # ---------- 音质 ----------
        score += self.FORMAT_SCORE.get(file.suffix.lower(), 0)

        # ---------- 长度 ----------
        normalized = self._simplify_name_for_length(name)
        target_len = sum(len(x) for x in self.song_names)
        score -= max(0, len(normalized) - target_len)
        # score -= max(0, len(name) - len(target))

        # ---------- 时间 ----------
        duration = self._get_duration(file)
        score += self._duration_score(duration)
        return score

    def _duration_score(self, duration: float) -> int:
        if duration < 30:
            return -100
        if duration < 60:
            return -80
        if duration < 90:
            return -50
        if duration <= 8 * 60:
            return 0
        if duration <= 12 * 60:
            return -10
        if duration <= 20 * 60:
            return -30
        if duration <= 40 * 60:
            return -60
        return -100

    @staticmethod
    def _split_words(name: str) -> list[str]:
        separators = (
            "-",
            "_",
            " ",
            "【",
            "】",
            "[",
            "]",
            "(",
            ")",
            "（",
            "）",
            ".",
            "·",
        )

        parts = [name]
        for sep in separators:
            new_parts = []
            for part in parts:
                new_parts.extend(part.split(sep))
            parts = new_parts

        return [part.strip() for part in parts if part.strip()]

    def _get_duration(self, file: Path) -> float:
        try:
            audio = File(file)
            if audio is None or audio.info is None:
                return 0
            return audio.info.length
        except Exception:
            return 0

    @staticmethod
    def _simplify_name_for_length(name: str) -> str:
        """
        规范化文件名，用于长度惩罚计算。

        处理内容：
        1. 去掉各种括号及其中内容，例如：
           晴天 (Live) -> 晴天
           晴天【Hi-Res】 -> 晴天
           晴天[Official] -> 晴天
        2. 去掉常见分隔符。
        3. 去掉所有空白字符。
        """

        # 去掉各种括号及其中内容（支持中英文括号）
        patterns = [
            r"\(.*?\)",  # ()
            r"（.*?）",  # （）
            r"\[.*?\]",  # []
            r"【.*?】",  # 【】
            r"<.*?>",  # <>
            r"《.*?》",  # 《》
            r"\{.*?\}",  # {}
            r"「.*?」",  # 「」
            r"『.*?』",  # 『』
        ]

        for pattern in patterns:
            name = re.sub(pattern, "", name)

        # 去掉常见分隔符
        name = re.sub(r"[-_.·•|]+", "", name)

        # 去掉所有空白字符
        name = re.sub(r"\s+", "", name)

        # # 去掉所有数字
        # name = re.sub(r"\d+", "", name)

        return name.strip()
    # def find_music_by_name(self) -> str | None:
    #     target = self.song_name.lower()  # 实现不区分大小写的包含匹配
    #
    #     for music_dir in self.music_dirs:
    #         if not music_dir.exists():
    #             logger.warning(f"音乐目录不存在: {music_dir}")
    #             continue
    #         result = self._search_in_dir(music_dir, target)
    #         if result:
    #             return result
    #
    #     return None
    #
    # def _search_in_dir(self, music_dir: Path, target: str) -> str | None:
    #     for file in music_dir.rglob("*"):
    #         # file.is_file() 确保它是文件而不是文件夹
    #         if not file.is_file():
    #             continue
    #         if file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
    #             continue
    #         if target in file.name.lower():
    #             file_path = str(file.resolve())
    #             logger.info(f"找到匹配的音乐文件: '{file.name}'，路径: {file_path}")
    #             return file_path  # 返回绝对路径的字符串形式
    #     return None

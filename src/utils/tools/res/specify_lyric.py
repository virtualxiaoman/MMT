from pathlib import Path
import re
import logging
from charset_normalizer import from_path
logger = logging.getLogger(__name__)


class LyricRepository:
    # 支持的歌词格式
    SUPPORTED_EXTENSIONS = {".txt", ".lrc"}

    # LRC时间标签
    LRC_TIME_PATTERN = re.compile(
        r"^\[\d{1,2}:\d{1,2}(?:\.\d+)?\]"
    )

    # LRC元数据
    LRC_META_PATTERN = re.compile(
        r"^\[(ti|ar|al|by|offset|re|ve|au):.*\]$",
        re.IGNORECASE
    )

    # 非歌词关键词
    META_KEYWORDS = (
        "词：",
        "曲：",
        "作词：",
        "作曲：",
        "编曲：",
        "制作人：",
        "制作：",
        "演唱：",
        "歌手：",
        "原唱：",
        "翻唱：",
    )
    # r"^(词|曲|编曲|制作人|作词|作曲|调教|调声|混音|母带|曲绘|绘图|画师|PV|视频|演唱|原唱|歌手|UP主|策划|企划|吉他|贝斯|鼓|和声|特别感谢|OP|SP)\s*[:：]"

    def __init__(self, lyric_dir: str | list[str]):
        if isinstance(lyric_dir, str):
            self.lyric_dirs = [Path(lyric_dir)]
        else:
            self.lyric_dirs = [Path(p) for p in lyric_dir]

    def find_next_line(self, lyric: str) -> str | None:
        """
        根据一句歌词寻找下一句
        """

        target = self._normalize_text(lyric)

        if not target:
            return None

        for lyric_dir in self.lyric_dirs:

            if not lyric_dir.exists():
                logger.warning(
                    f"歌词目录不存在: {lyric_dir}"
                )
                continue

            for file in lyric_dir.rglob("*"):

                if (
                        not file.is_file()
                        or file.suffix.lower()
                        not in self.SUPPORTED_EXTENSIONS
                ):
                    continue

                result = self._search_file(
                    file,
                    target
                )

                if result:
                    return result

        return None

    def _search_file(
            self,
            lyric_file: Path,
            target: str
    ) -> str | None:

        lines = self._load_lyrics(lyric_file)

        if not lines:
            return None

        for idx, line in enumerate(lines):

            if line != target:
                continue

            if idx + 1 < len(lines):
                return lines[idx + 1]

            return (
                f"这首《{lyric_file.stem}》"
                "你喜欢吗？"
            )

        return None

    def _load_lyrics(self, lyric_file: Path):

        result = from_path(lyric_file)

        best = result.best()

        if best is None:
            return []

        text = str(best)

        lines = text.splitlines()

        return [
            self._clean_line(line)
            for line in lines
            if self._clean_line(line)
        ]

    def _clean_line(
            self,
            line: str
    ) -> str | None:
        """
        将原始歌词行转换成纯歌词
        """

        line = line.strip()

        if not line:
            return None

        # ---------
        # LRC时间戳
        # ---------

        line = self.LRC_TIME_PATTERN.sub(
            "",
            line
        )

        # ---------
        # LRC标签
        # ---------

        if self.LRC_META_PATTERN.match(line):
            return None

        # ---------
        # 空白
        # ---------

        line = line.strip()

        if not line:
            return None

        # ---------
        # txt头信息过滤
        # ---------

        if self._is_meta_line(line):
            return None

        return self._normalize_text(line)

    def _is_meta_line(
            self,
            line: str
    ) -> bool:
        """
        判断是否为歌曲信息
        """

        for keyword in self.META_KEYWORDS:

            if line.startswith(keyword):
                return True

        # 例如：
        # hello&bye，days - COP
        # 歌名-歌手
        #
        # 这种通常在txt第一行
        #
        if (
                " - " in line
                and len(line) < 80
        ):
            return True

        return False

    def _normalize_text(
            self,
            text: str
    ) -> str:
        """
        用于匹配的文本标准化
        """

        text = text.strip()

        # 多个连续空格压缩成一个
        text = re.sub(
            r"[ \t]+",
            " ",
            text
        )

        return text
# class LyricRepository:
#
#     def __init__(self, lyric_dir: str | list[str]):
#         if isinstance(lyric_dir, str):
#             self.lyric_dirs = [Path(lyric_dir)]
#         else:
#             self.lyric_dirs = [Path(p) for p in lyric_dir]
#
#     def find_next_line(self, lyric: str) -> str | None:
#         target = lyric.strip()
#         for lyric_dir in self.lyric_dirs:
#             if not lyric_dir.exists():
#                 logger.warning(f"歌词目录不存在: {lyric_dir}")
#                 continue
#             for txt_file in lyric_dir.rglob("*.txt"):
#                 result = self._search_file(txt_file, target)
#                 if result is not None:
#                     return result
#         return None
#
#     def _search_file(self, txt_file: Path, target: str) -> str | None:
#         try:
#             with open(txt_file, "r", encoding="utf-8") as f:
#                 lines = [line.strip() for line in f if line.strip()]
#         except Exception as e:
#             logger.warning(f"读取歌词失败: {txt_file} {e}")
#             return None
#
#         for idx, line in enumerate(lines):
#             if len(line) == 1:
#                 return None
#             if line != target:
#                 continue
#             if idx < len(lines) - 1:
#                 return lines[idx + 1]
#             song_name = txt_file.stem
#             return f"这首《{song_name}》你喜欢吗？"
#
#         return None

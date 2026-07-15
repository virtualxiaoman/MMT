from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class LyricRepository:

    def __init__(self, lyric_dir: str | list[str]):
        if isinstance(lyric_dir, str):
            self.lyric_dirs = [Path(lyric_dir)]
        else:
            self.lyric_dirs = [Path(p) for p in lyric_dir]

    def find_next_line(self, lyric: str) -> str | None:
        target = lyric.strip()
        for lyric_dir in self.lyric_dirs:
            if not lyric_dir.exists():
                logger.warning(f"歌词目录不存在: {lyric_dir}")
                continue
            for txt_file in lyric_dir.rglob("*.txt"):
                result = self._search_file(txt_file, target)
                if result is not None:
                    return result
        return None

    def _search_file(self, txt_file: Path, target: str) -> str | None:
        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.warning(f"读取歌词失败: {txt_file} {e}")
            return None

        for idx, line in enumerate(lines):
            if line != target:
                continue
            if idx < len(lines) - 1:
                return lines[idx + 1]
            song_name = txt_file.stem
            return f"这首《{song_name}》你喜欢吗？"

        return None

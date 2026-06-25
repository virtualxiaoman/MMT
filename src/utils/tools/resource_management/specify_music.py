from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MusicRepository:
    # 支持的音频文件扩展名
    SUPPORTED_EXTENSIONS = {
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".m4a",
        ".aac"
    }

    def __init__(self, song_name: str, music_dirs: str | list):
        self.song_name = song_name

        if isinstance(music_dirs, str):
            self.music_dirs = [Path(music_dirs)]
        else:
            self.music_dirs = [
                Path(path)
                for path in music_dirs
            ]

    def find_music_by_name(self) -> str | None:
        target = self.song_name.lower()  # 实现不区分大小写的包含匹配

        for music_dir in self.music_dirs:
            if not music_dir.exists():
                logger.warning(f"音乐目录不存在: {music_dir}")
                continue
            result = self._search_in_dir(music_dir, target)
            if result:
                return result

        return None

    def _search_in_dir(self, music_dir: Path, target: str) -> str | None:
        for file in music_dir.rglob("*"):
            # file.is_file() 确保它是文件而不是文件夹
            if not file.is_file():
                continue
            if file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
            if target in file.name.lower():
                file_path = str(file.resolve())
                logger.info(f"找到匹配的音乐文件: '{file.name}'，路径: {file_path}")
                return file_path  # 返回绝对路径的字符串形式
        return None


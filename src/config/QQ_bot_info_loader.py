from dataclasses import dataclass, field
from pathlib import Path
import yaml

from src.config.path import EMOJI_DIR, QQ_BOT_INFO_DIR


@dataclass(frozen=True)
class BotPaths:
    music_dirs: list[str] = field(default_factory=list)
    random_picture_dirs: list[str] = field(default_factory=list)
    lyric_dirs: list[str] = field(default_factory=list)
    emoji_dir: str = ""


@dataclass(frozen=True)
class BotConfig:
    name_zh: str
    name_en: str
    nickname: list[str]
    bot_id: int
    admin_qq_id: int
    paths: BotPaths


class BotInfoConfigLoader:

    @classmethod
    def load(cls, bot_name: str) -> BotConfig:
        config_path = Path(QQ_BOT_INFO_DIR) / f"{bot_name}.yaml"

        if not config_path.exists():
            raise FileNotFoundError(
                f"Bot配置文件不存在: {config_path}"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        paths_data = data.get("paths", {})

        paths = BotPaths(
            music_dirs=list(paths_data.get("music_dirs", [])),
            random_picture_dirs=list(paths_data.get("random_picture_dirs", [])),
            lyric_dirs=list(paths_data.get("lyric_dirs", [])),
            # 优先读 yaml 中配置的表情目录；未配置时回退到 assets/emoji/<bot>。
            emoji_dir=str(paths_data.get("emoji_dir") or EMOJI_DIR / bot_name),
        )

        return BotConfig(
            name_zh=data["name_zh"],
            name_en=data["name_en"],
            nickname=data["nickname"],
            bot_id=data["bot_id"],
            admin_qq_id=data.get("admin_qq_id", []),
            paths=paths
        )


if __name__ == "__main__":
    config = BotInfoConfigLoader.load("LuoTianyi")

    print(config.name_zh)
    print(config.bot_id)

    print(config.paths.music_dirs)
    print(config.paths.random_picture_dirs)
    print(config.paths.lyric_dirs)

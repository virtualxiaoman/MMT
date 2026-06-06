from dataclasses import dataclass, field
from pathlib import Path
import yaml

from src.config.path import QQ_BOT_INFO_DIR


@dataclass(frozen=True)
class BotPaths:
    music_dirs: list[str] = field(default_factory=list)
    random_picture_dirs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BotConfig:
    name: str
    qq_id: int
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
            random_picture_dirs=list(paths_data.get("random_picture_dirs", []))
        )

        return BotConfig(
            name=data["name"],
            qq_id=data["qq_id"],
            paths=paths
        )


if __name__ == "__main__":
    config = BotConfigLoader.load("LuoTianyi")

    print(config.name)
    print(config.qq_id)

    print(config.paths.music_dirs)
    print(config.paths.random_picture_dirs)

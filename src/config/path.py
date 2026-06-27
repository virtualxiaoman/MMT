from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

ASSETS_DIR = PROJECT_ROOT / "assets"

API_KEY_DIR = ASSETS_DIR / "api_key"
PROMPT_DIR = ASSETS_DIR / "prompt"
CONFIG_DIR = ASSETS_DIR / "config"
EMOJI_DIR = ASSETS_DIR / "emoji"
VOICE_DIR = ASSETS_DIR / "voice"
HISTORY_DIR = ASSETS_DIR / "history"
PICTURES_DIR = ASSETS_DIR / "pictures"

QQ_BOT_INFO_DIR = CONFIG_DIR / "QQ_bot_info"

# print(f"项目根目录: {PROJECT_ROOT}")
# print(f"资源目录: {ASSETS_DIR}")
# print(f"API Key 目录: {API_KEY_DIR}")
# print(f"Prompt 目录: {PROMPT_DIR}")

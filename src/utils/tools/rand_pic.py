import random
from pathlib import Path
from typing import Union, List


class RandomPicture:
    def __init__(self, paths: Union[str, List[str]]):
        """
        初始化图片选择器
        :param paths: 路径字符串或列表（支持相对/绝对路径）
        """
        if isinstance(paths, str):
            self.input_paths = [paths]
        else:
            self.input_paths = paths

        self.valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
        self.all_images = self._scan_images()

    def _scan_images(self) -> List[Path]:
        """使用 rglob 递归扫描所有子目录下的图片"""
        found_images = []
        for p in self.input_paths:
            path_obj = Path(p).resolve()

            if path_obj.is_dir():
                # '*' 代表匹配所有文件，rglob 会自动递归进入所有子文件夹
                # 如果只想匹配特定后缀，也可以用 rglob('*.jpg')，但由于我们要匹配多种，
                # 遍历后手动判断后缀通常更灵活。
                for file in path_obj.rglob('*'):
                    if file.is_file() and file.suffix.lower() in self.valid_extensions:
                        found_images.append(file)
            else:
                print(f"提示: 路径 {p} 不存在或不是目录，已跳过。")

        return found_images

    def get_random_image_path(self) -> str:
        """随机返回一个图片文件的绝对路径"""
        if not self.all_images:
            return "未在指定目录及其子目录中找到任何图片文件。"

        return str(random.choice(self.all_images))


# --- 使用示例 ---
if __name__ == "__main__":
    # 示例 1: 传入单个相对路径
    # picker = ImagePicker("./my_images")

    # 示例 2: 传入多个路径（包含绝对和相对）
    paths_to_search = [
        "F:/Picture/pixiv/BA",
        "F:/Picture/pixiv/甘城",
        "F:/Picture/pixiv/LuoTianyi"
    ]

    random_image = RandomPicture(paths_to_search)
    print(f"一共找到 {len(random_image.all_images)} 张图片。")

    # 获取随机图片路径
    random_path = random_image.get_random_image_path()
    print(f"随机选取的图片路径是: {random_path}")

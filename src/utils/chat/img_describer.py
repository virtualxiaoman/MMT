import base64
import requests
from pathlib import Path
import dashscope
from dashscope import MultiModalConversation
import io
from src.config.path import API_KEY_DIR
from src.utils.tools.file import load_from_txt
from PIL import Image


class ImageResizer:

    @staticmethod
    def resize(
            image: Image.Image,
            max_pixels: int = 768 * 768
    ) -> Image.Image:
        """
        按总像素数等比例缩放图片。
        """

        width, height = image.size

        current_pixels = width * height

        if current_pixels <= max_pixels:
            return image

        scale = (max_pixels / current_pixels) ** 0.5

        new_width = int(width * scale)
        new_height = int(height * scale)

        return image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )

    @staticmethod
    def convert_to_rgb(
            image: Image.Image
    ) -> Image.Image:
        """
        统一转换为 RGB。
        自动处理透明背景。
        """

        if image.mode == "RGBA":
            background = Image.new(
                "RGB",
                image.size,
                (255, 255, 255)
            )

            background.paste(
                image,
                mask=image.split()[3]
            )

            return background

        if image.mode != "RGB":
            return image.convert("RGB")

        return image

    @classmethod
    def preprocess(
            cls,
            image: Image.Image,
            max_pixels: int = 768 * 768
    ) -> Image.Image:
        """
        图片预处理：
        1. 缩放
        2. RGB转换
        """

        image = cls.resize(
            image=image,
            max_pixels=max_pixels
        )

        image = cls.convert_to_rgb(
            image=image
        )

        return image


class ImageDescriber:

    def __init__(
            self,
            api_key: str | None = None,
            model: str = "qwen3-vl-plus",
            max_pixels: int = 768 * 768
    ):
        if api_key is not None:
            dashscope.api_key = api_key
        else:
            dashscope.api_key = load_from_txt(Path(API_KEY_DIR) / "qwen.txt")

        self.model = model
        self.max_pixels = max_pixels

    def describe_img(
            self,
            image_url: str
    ) -> str:
        image_base64 = self._image_url_to_base64(
            image_url=image_url
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": image_base64
                    },
                    {
                        "text":
                            """
请分析这张图片，并生成适合作为聊天上下文的图片描述。
要求：
1. 说明图片类型（照片、动漫、表情包、截图、风景、游戏画面等）。
2. 描述图片中的人物、动物、物体、场景、动作、表情、服装、环境等可见信息。
3. 如果图中人物存在明显情绪或表情，请说明。
4. 如果存在文字，请完整地提取文字内容，不要遗漏
5. 不要分析，不要评价，不要推测用户意图。客观描述图片中实际出现的内容，不要编造不存在的信息。
6. 使用一段简洁自然语言描述，控制在150字以内（但注意OCR内容不计入字数中，也就是即使OCR出来的文字很长，也全部输出）。
"""
                    }
                ]
            }
        ]

        response = MultiModalConversation.call(
            model=self.model,
            messages=messages
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"图片识别失败: {response.message}"
            )

        return (
            response.output
            .choices[0]
            .message
            .content[0]["text"]
        )

    def _image_url_to_base64(
            self,
            image_url: str
    ) -> str:
        response = requests.get(
            image_url,
            timeout=20
        )

        response.raise_for_status()

        image = Image.open(
            io.BytesIO(response.content)
        )

        image = ImageResizer.preprocess(
            image=image,
            max_pixels=self.max_pixels
        )

        buffer = io.BytesIO()

        image.save(
            buffer,
            format="JPEG",
            quality=90,
            optimize=True
        )

        image_bytes = buffer.getvalue()

        image_base64 = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        return (
            f"data:image/jpeg;base64,{image_base64}"
        )

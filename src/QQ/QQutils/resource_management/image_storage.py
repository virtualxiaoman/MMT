from __future__ import annotations

import hashlib
import io
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

from src.config.path import HISTORY_DIR


class ImageStorage:
    """
    图片存储器

    功能：
    1. 下载图片（image / qq_emoji）
    2. SHA256 去重
    3. 保存原图
    4. 更新 MessageWrapper 中的 file 字段
    """

    EXT_MAPPING = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
        "BMP": ".bmp",
        "TIFF": ".tiff",
    }

    def __init__(
            self,
            bot_id: int | str,
    ) -> None:
        self.history_dir = Path(HISTORY_DIR)
        self.bot_id = str(bot_id)

        self.bot_root = (
                self.history_dir
                / "qq_chat"
                / self.bot_id
        )

        self.bot_root.mkdir(
            parents=True,
            exist_ok=True
        )

        self.db_path = self.bot_root / "image_index.db"

        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        self._init_database()

    # ==========================================================
    # sqlite
    # ==========================================================

    def _init_database(self) -> None:
        """
        初始化数据库
        """

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS images(
            sha256 TEXT PRIMARY KEY,
            relative_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            created_time TEXT NOT NULL
        )
        """)

        self.conn.commit()

    def close(self):
        self.conn.close()

    # ==========================================================
    # hash
    # ==========================================================

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    # ==========================================================
    # 下载图片
    # ==========================================================

    @staticmethod
    def _download(url: str) -> bytes:
        """
        下载原图
        """

        response = requests.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        return response.content

    # ==========================================================
    # 图片格式
    # ==========================================================

    @classmethod
    def _detect_suffix(cls, data: bytes) -> str:
        """
        根据图片内容判断后缀
        """

        image = Image.open(io.BytesIO(data))

        fmt = image.format.upper()

        if fmt not in cls.EXT_MAPPING:
            raise ValueError(
                f"暂不支持图片格式：{fmt}"
            )

        return cls.EXT_MAPPING[fmt]

    # ==========================================================
    # sqlite 查询
    # ==========================================================

    def _query_image(
            self,
            sha256: str
    ) -> str | None:

        self.cursor.execute(
            """
            SELECT relative_path
            FROM images
            WHERE sha256=?
            """,
            (sha256,)
        )

        result = self.cursor.fetchone()

        if result is None:
            return None

        return result[0]

    def _insert_image(
            self,
            sha256: str,
            relative_path: str,
            file_size: int,
    ) -> None:

        self.cursor.execute(
            """
            INSERT INTO images(
                sha256,
                relative_path,
                file_size,
                created_time
            )
            VALUES(?,?,?,?)
            """,
            (
                sha256,
                relative_path,
                file_size,
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )

        self.conn.commit()

    # ==========================================================
    # 自动编号
    # ==========================================================

    def _next_filename(
            self,
            image_type: str,
            suffix: str,
            date: str,
    ) -> tuple[str, Path]:
        """
        返回

        image/
            2026-06/
                2026-06-27-1.jpg
        """

        month = date[:7]

        folder = (
                self.bot_root
                / image_type
                / month
        )

        folder.mkdir(
            parents=True,
            exist_ok=True
        )

        prefix = f"{date}-"

        max_id = 0

        for file in folder.iterdir():

            if not file.is_file():
                continue

            if not file.name.startswith(prefix):
                continue

            stem = file.stem

            try:
                idx = int(
                    stem.replace(prefix, "")
                )
            except ValueError:
                continue

            max_id = max(max_id, idx)

        filename = f"{date}-{max_id + 1}{suffix}"

        return (
            filename,
            folder / filename
        )

    # ==========================================================
    # 保存原图
    # ==========================================================

    @staticmethod
    def _write_file(
            path: Path,
            data: bytes
    ) -> None:

        with open(
                path,
                "wb"
        ) as f:
            f.write(data)

    # ==========================================================
    # 保存单张图片
    # ==========================================================

    def _save_image(
            self,
            image_url: str,
            image_type: str,
            date: str,
    ) -> str:
        """
        下载并保存图片。

        Returns
        -------
        str
            图片相对路径，例如：
            image/2026-06/2026-06-27-3.webp
        """

        # 下载原图
        data = self._download(image_url)

        # SHA256
        sha256 = self._sha256(data)

        # 查重
        old_path = self._query_image(sha256)

        if old_path is not None:

            full_path = self.bot_root / old_path

            # 数据库存在且文件真实存在
            if full_path.exists():
                return old_path

            # 数据库存在，但文件被用户删除
            print(
                f"[ImageStorage] 图片丢失，重新保存：{old_path}"
            )

        # 判断图片格式
        suffix = self._detect_suffix(data)

        # 自动编号
        filename, save_path = self._next_filename(
            image_type=image_type,
            suffix=suffix,
            date=date
        )

        # 保存原图
        self._write_file(
            save_path,
            data
        )

        relative_path = (
                Path(image_type)
                / date[:7]
                / filename
        ).as_posix()

        # 数据库已有该 sha，说明只是图片被删了
        if old_path is not None:

            self.cursor.execute(
                """
                UPDATE images
                SET
                    relative_path=?,
                    file_size=?,
                    created_time=?
                WHERE sha256=?
                """,
                (
                    relative_path,
                    len(data),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    sha256
                )
            )

            self.conn.commit()

        else:

            self._insert_image(
                sha256=sha256,
                relative_path=relative_path,
                file_size=len(data)
            )

        return relative_path

    # ==========================================================
    # 对 MessageWrapper 进行处理
    # ==========================================================

    def process(
            self,
            message_wrapper,
    ):
        """
        下载 MessageWrapper 中所有图片，并填写 file 字段。
        """

        date = datetime.fromtimestamp(
            message_wrapper.timestamp
        ).strftime("%Y-%m-%d")

        for seg in message_wrapper.segments:

            seg_type = seg["type"]

            if seg_type not in (
                    "image",
                    "qq_emoji"
            ):
                continue

            if seg.get("file"):
                continue

            url = seg.get("url")

            if not url:
                continue

            try:

                seg["file"] = self._save_image(
                    image_url=url,
                    image_type=seg_type,
                    date=date
                )

            except Exception as e:

                print(
                    "[ImageStorage] "
                    f"保存图片失败：{e}"
                )

        return message_wrapper

    # ==========================================================
    # 上下文管理器
    # ==========================================================

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        self.close()

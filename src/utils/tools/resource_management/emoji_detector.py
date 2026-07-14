from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import requests

from src.config.path import EMOJI_HASH_DIR


class EmojiDetector:
    """
    判断网络图片是否属于本地表情包库。

    使用 SHA-256 精确匹配。

    初始化时自动同步 SQLite 数据库，
    所有 SHA256 会加载到内存 set 中，
    后续判断复杂度为 O(1)。
    """

    IMAGE_SUFFIXES = {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".webp",
    }

    def __init__(
            self,
            emoji_dir: str | Path,
            cache_dir: str | Path = EMOJI_HASH_DIR,
    ):
        self.emoji_dir = Path(emoji_dir)

        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = cache_dir / f"{self.emoji_dir.name}.db"

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        self.session = requests.Session()

        self._create_table()
        self._sync_database()

        self.sha_set = self._load_sha_set()

    # ==========================================================
    # Public
    # ==========================================================

    def is_emoji(self, image_url: str) -> bool:
        """
        判断网络图片是否属于表情包库。
        """
        # 检测是不是字符串，是不是合法的图片 URL
        if not isinstance(image_url, str):
            print(f"image_url 不是字符串: {image_url}")
            return False
        if not image_url.lower().startswith(("http://", "https://")):
            print(f"image_url 不是合法的 URL: {image_url}")
            return False
        try:
            data = self._download(image_url)
            sha = self._calc_sha256_bytes(data)
            # print("network:", sha)
            # print("exist:", sha in self.sha_set)
        except Exception as e:
            print(f"下载图片失败: {image_url}，错误: {e}")
            return False

        return sha in self.sha_set

    def close(self):
        self.session.close()
        self.conn.close()

    # ==========================================================
    # Database
    # ==========================================================

    def _create_table(self):

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS emoji(

                path TEXT PRIMARY KEY,

                mtime REAL NOT NULL,

                size INTEGER NOT NULL,

                sha256 TEXT NOT NULL
            )
            """
        )

        self.conn.commit()

    def _sync_database(self):

        cursor = self.conn.cursor()

        db_files = {}

        for row in cursor.execute(
                """
                SELECT path,mtime,size
                FROM emoji
                """
        ):
            db_files[row["path"]] = (
                row["mtime"],
                row["size"],
            )

        disk_files = {}

        for file in self.emoji_dir.rglob("*"):

            if not file.is_file():
                continue

            if file.suffix.lower() not in self.IMAGE_SUFFIXES:
                continue

            stat = file.stat()

            rel_path = file.relative_to(self.emoji_dir).as_posix()

            disk_files[rel_path] = (
                stat.st_mtime,
                stat.st_size,
                file,
            )

        # 删除数据库中已经不存在的图片

        for path in set(db_files) - set(disk_files):
            cursor.execute(
                "DELETE FROM emoji WHERE path=?",
                (path,),
            )

        # 新增或更新

        for rel_path, (mtime, size, file) in disk_files.items():

            update = False

            if rel_path not in db_files:
                update = True
            else:
                old_mtime, old_size = db_files[rel_path]

                if old_mtime != mtime or old_size != size:
                    update = True

            if update:
                sha = self._calc_sha256(file)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO emoji
                    (
                        path,
                        mtime,
                        size,
                        sha256
                    )
                    VALUES (?,?,?,?)
                    """,
                    (
                        rel_path,
                        mtime,
                        size,
                        sha,
                    ),
                )

        self.conn.commit()

    def _load_sha_set(self) -> set[str]:

        cursor = self.conn.execute(
            """
            SELECT sha256
            FROM emoji
            """
        )

        return {
            row["sha256"]
            for row in cursor
        }

    # ==========================================================
    # SHA256
    # ==========================================================

    @staticmethod
    def _calc_sha256(file: Path) -> str:

        h = hashlib.sha256()

        with file.open("rb") as f:

            while True:

                chunk = f.read(1024 * 1024)

                if not chunk:
                    break

                h.update(chunk)

        return h.hexdigest()

    @staticmethod
    def _download(url: str) -> bytes:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _calc_sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    emoji_detector = EmojiDetector(
        emoji_dir=r"D:\Users\Administrator\Desktop\Emoji\LuoTianyi",
    )
    print(emoji_detector._calc_sha256(Path(r"D:\Users\Administrator\Desktop\Emoji\LuoTianyi\探头.jpg")))
    test_url = "https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=EhRhQHjb1gOKhfNAj5K8vFj45itAJRi92gIg_gooksWOkO3PlQMyBHByb2RQgLsvWhCu8LFaYy91vEFoRErxOXXAegJuPYIBAmd6&rkey=CAQSMLZByR-pFjttB2Qz6hACUflyATJX5RhqSSABGczxLtGIg3d-YBqOD4uz-WINwnyyNQ"
    is_emoji = emoji_detector.is_emoji(test_url)

    print(f"{test_url} is emoji: {is_emoji}")

    emoji_detector.close()

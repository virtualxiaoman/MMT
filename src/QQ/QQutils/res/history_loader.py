from __future__ import annotations
import re
from datetime import datetime, date
from pathlib import Path
from typing import Generator

from src.config.path import QQ_HISTORY_DIR


class HistoryLoader:
    """
    聊天历史加载器。

    本类仅负责读取聊天历史，不涉及任何 LLM 或 Summary 逻辑。

    提供以下能力：

        1. 读取最近 N 条聊天记录。
        2. 读取今天全部聊天记录。
        3. 读取指定日期聊天记录。
        4. 按天遍历整个 Session 的聊天记录。
        5. 按固定消息数遍历整个 Session（iter_chunks）。

    聊天记录支持消息内包含任意换行。

    消息起始格式固定为：

        [2026-07-13 09:59:32]

    下一条时间戳即表示上一条消息结束。

    目录结构：

        QQ_HISTORY_DIR/
            bot_id/
                private/
                    session_id/
                        llm_input/
                            2026-07/
                                2026-07-01.txt
                                ...

                group/
                    session_id/
                        llm_input/
                            2026-07/
                                ...
    """

    DEFAULT_MAX_LINES = 100
    DEFAULT_CHUNK_SIZE = 500

    _MESSAGE_HEADER = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] .+?：")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def load_last(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            max_lines: int = DEFAULT_MAX_LINES,
    ) -> str:
        """
        读取最近 max_lines 条消息（仅今天）。
        """

        return "\n".join(
            cls.load_last_list(
                bot_id,
                is_private,
                session_id,
                max_lines,
            )
        )

    @classmethod
    def load_last_list(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            max_lines: int = DEFAULT_MAX_LINES,
    ) -> list[str]:
        """
        读取最近 max_lines 条消息（仅今天）。

        Returns
        -------
        list[str]
        """

        if max_lines <= 0:
            raise ValueError("max_lines 必须大于0。")

        file = cls._get_history_file(
            bot_id,
            is_private,
            session_id,
            datetime.now().date(),
        )

        if not file.exists():
            return []

        messages = cls._split_messages(cls._read_all(file))
        return messages[-max_lines:]

    @classmethod
    def load_today(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> str:
        """
        读取今天全部聊天记录。
        """

        return "\n".join(
            cls.load_today_list(
                bot_id,
                is_private,
                session_id,
            )
        )

    @classmethod
    def load_today_list(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> list[str]:
        """
        读取今天全部聊天记录。

        Returns
        -------
        list[str]
        """

        return cls.load_date_list(
            bot_id,
            is_private,
            session_id,
            datetime.now().date(),
        )

    @classmethod
    def load_date(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            target_date: date,
    ) -> str:
        """
        读取指定日期全部聊天记录。
        """

        return "\n".join(
            cls.load_date_list(
                bot_id,
                is_private,
                session_id,
                target_date,
            )
        )

    @classmethod
    def load_date_list(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            target_date: date,
    ) -> list[str]:
        """
        读取指定日期全部聊天记录。

        Returns
        -------
        list[str]
        """

        file = cls._get_history_file(
            bot_id,
            is_private,
            session_id,
            target_date,
        )

        if not file.exists():
            return []

        return cls._split_messages(cls._read_all(file))

    @classmethod
    def iter_daily(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> Generator[tuple[date, str], None, None]:
        """
        按日期遍历聊天记录。
        """

        for day, file in cls.iter_files(bot_id, is_private, session_id):
            history = cls._read_all(file)
            if history.strip():
                yield day, history

    @classmethod
    def iter_chunks(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Generator[tuple[date, date, str], None, None]:
        """
        按固定消息数遍历整个 Session。

        一个 Chunk 可以跨越多个日期。

        Yields
        ------
        (
            起始日期,
            结束日期,
            聊天记录
        )
        """

        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于0。")

        buffer: list[str] = []
        start_date: date | None = None
        end_date: date | None = None

        for day, history in cls.iter_daily(bot_id, is_private, session_id):
            messages = cls._split_messages(history)

            if not messages:
                continue

            for message in messages:
                if not message.strip():
                    continue

                if not buffer:
                    start_date = day

                end_date = day
                buffer.append(message)

                if len(buffer) >= chunk_size:
                    yield start_date, end_date, "\n".join(buffer)
                    buffer.clear()
                    start_date = None
                    end_date = None

        if buffer:
            yield start_date, end_date, "\n".join(buffer)

    @classmethod
    def iter_files(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> Generator[tuple[date, Path], None, None]:
        """
        按时间顺序遍历当前 Session 的所有历史聊天文件。

        Yields
        ------
        tuple[date, Path]

            (
                datetime.date,
                txt文件路径
            )
        """

        history_dir = cls._get_history_dir(bot_id, is_private, session_id)

        if not history_dir.exists():
            return

        for month_dir in sorted(p for p in history_dir.iterdir() if p.is_dir()):
            for file in sorted(month_dir.glob("*.txt")):
                try:
                    day = datetime.strptime(file.stem, "%Y-%m-%d").date()
                except ValueError:
                    continue

                yield day, file

    @classmethod
    def count(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> int:
        """
        获取当前 Session 总消息数量。
        用于 SummaryManager 判断是否需要更新 short_term。
        """
        total = 0
        for _, file in cls.iter_files(
                bot_id,
                is_private,
                session_id,
        ):
            history = cls._read_all(file)
            total += len(cls._split_messages(history))
        return total

    @classmethod
    def count_today(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> int:
        """
        获取当前 Session 总消息数量。
        用于 SummaryManager 判断是否需要更新 short_term。
        """
        return len(
            cls.load_today_list(
                bot_id,
                is_private,
                session_id,
            )
        )

    @classmethod
    def load_range(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            start: int,
            end: int,
    ) -> str:
        """
        按全局消息索引读取历史。

        参数：
            start:
                起始消息编号（包含）

            end:
                结束消息编号（不包含）

        例如：

            load_range(100, 150)

        返回第100~149条消息。

        """

        if start < 0:
            raise ValueError("start不能小于0")

        if end <= start:
            return ""

        result = []

        index = 0

        for _, file in cls.iter_files(
                bot_id,
                is_private,
                session_id,
        ):

            history = cls._read_all(file)

            messages = cls._split_messages(history)

            for message in messages:

                if index >= end:
                    break

                if index >= start:
                    result.append(message)

                index += 1

            if index >= end:
                break

        return "\n".join(result)

    @classmethod
    def load_today_range(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            start: int,
            end: int,
    ) -> str:

        messages = cls.load_today_list(
            bot_id,
            is_private,
            session_id,
        )
        if start < end:
            return "\n".join(
                messages[start:end]
            )
        else:
            return None

    @classmethod
    def get_first_date(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> date | None:
        """
        获取当前 Session 最早的聊天日期。

        Returns
        -------
        date | None
            如果不存在聊天记录，则返回 None。
        """

        for day, _ in cls.iter_files(bot_id, is_private, session_id):
            return day

        return None

    @classmethod
    def get_last_date(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> date | None:
        """
        获取当前 Session 最新的聊天日期。

        Returns
        -------
        date | None
            如果不存在聊天记录，则返回 None。
        """

        last_day = None

        for day, _ in cls.iter_files(bot_id, is_private, session_id):
            last_day = day

        return last_day

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _get_session_dir(
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> Path:
        """
        获取 Session 根目录。

        返回：

            QQ_HISTORY_DIR/
                bot_id/
                    private/
                        session_id/

        或

            QQ_HISTORY_DIR/
                bot_id/
                    group/
                        session_id/
        """

        session_type = "private" if is_private else "group"
        return Path(QQ_HISTORY_DIR) / str(bot_id) / session_type / str(session_id)

    @classmethod
    def _get_history_dir(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
    ) -> Path:
        """
        获取 llm_input 根目录。
        """

        return cls._get_session_dir(bot_id, is_private, session_id) / "llm_input"

    @classmethod
    def _get_history_file(
            cls,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            target_date: date,
    ) -> Path:
        """
        获取指定日期对应的聊天记录文件。
        """

        month = target_date.strftime("%Y-%m")
        filename = target_date.strftime("%Y-%m-%d") + ".txt"

        return cls._get_history_dir(bot_id, is_private, session_id) / month / filename

    @staticmethod
    def _read_all(file_path: Path) -> str:
        """
        读取整个文件。
        """

        return file_path.read_text(encoding="utf-8")

    @classmethod
    def _split_messages(cls, history: str) -> list[str]:
        """
        将聊天记录拆分为消息。

        每条消息必须以：

            [2026-07-13 09:59:32]

        开头。

        消息正文允许包含任意数量的换行。
        """

        if not history.strip():
            return []

        messages: list[str] = []
        current: list[str] = []

        for line in history.splitlines():
            if cls._MESSAGE_HEADER.match(line):
                if current:
                    messages.append("\n".join(current))
                current = [line]
            elif current:
                current.append(line)
            else:
                # 兼容异常或旧格式数据
                current = [line]

        if current:
            messages.append("\n".join(current))

        return messages

    @classmethod
    def _read_last_messages(
            cls,
            file_path: Path,
            max_messages: int,
    ) -> str:
        """
        读取最后 max_messages 条消息。
        """

        messages = cls._split_messages(file_path.read_text(encoding="utf-8"))

        if len(messages) <= max_messages:
            return "\n".join(messages)

        return "\n".join(messages[-max_messages:])


# class HistoryLoader:
#     """
#     聊天历史加载器。
#
#     本类仅负责读取聊天历史，不涉及任何 LLM 或 Summary 逻辑。
#
#     提供以下能力：
#
#         1. 读取最近 N 条聊天记录。
#         2. 读取今天全部聊天记录。
#         3. 读取指定日期聊天记录。
#         4. 按天遍历整个 Session 的聊天记录。
#         5. 按固定消息数遍历整个 Session（iter_chunks）。
#
#     目录结构：
#
#         QQ_HISTORY_DIR/
#             bot_id/
#                 private/
#                     session_id/
#                         llm_input/
#                             2026-07/
#                                 2026-07-01.txt
#                                 2026-07-02.txt
#                                 ...
#
#                 group/
#                     session_id/
#                         llm_input/
#                             2026-07/
#                                 ...
#     """
#
#     DEFAULT_MAX_LINES = 100
#
#     DEFAULT_CHUNK_SIZE = 500
#
#     # ------------------------------------------------------------------
#     # Public API
#     # ------------------------------------------------------------------
#
#     @classmethod
#     def load_last(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#             max_lines: int = DEFAULT_MAX_LINES,
#     ) -> str:
#         """
#         读取最近 max_lines 条聊天记录（仅今天）。
#
#         Parameters
#         ----------
#         bot_id
#             Bot QQ。
#
#         is_private
#             是否私聊。
#
#         session_id
#             会话ID。
#
#         max_lines
#             最近多少条。
#
#         Returns
#         -------
#         str
#         """
#
#         if max_lines <= 0:
#             raise ValueError("max_lines 必须大于0。")
#
#         file = cls._get_history_file(
#             bot_id,
#             is_private,
#             session_id,
#             datetime.now().date(),
#         )
#
#         if not file.exists():
#             return ""
#
#         return cls._read_last_lines(
#             file,
#             max_lines,
#         )
#
#     @classmethod
#     def load_today(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#     ) -> str:
#         """
#         读取今天全部聊天记录。
#         """
#
#         return cls.load_date(
#             bot_id,
#             is_private,
#             session_id,
#             datetime.now().date(),
#         )
#
#     @classmethod
#     def load_date(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#             target_date: date,
#     ) -> str:
#         """
#         读取指定日期全部聊天记录。
#
#         Parameters
#         ----------
#         target_date
#             datetime.date。
#         """
#
#         file = cls._get_history_file(
#             bot_id,
#             is_private,
#             session_id,
#             target_date,
#         )
#
#         if not file.exists():
#             return ""
#
#         return cls._read_all(file)
#
#     @classmethod
#     def iter_daily(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#     ) -> Generator[tuple[date, str], None, None]:
#         """
#         按日期遍历聊天记录。
#         """
#
#         for day, file in cls.iter_files(
#                 bot_id,
#                 is_private,
#                 session_id,
#         ):
#
#             history = cls._read_all(file)
#
#             if history.strip():
#                 yield day, history
#
#     @classmethod
#     def iter_chunks(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#             chunk_size: int = DEFAULT_CHUNK_SIZE,
#     ) -> Generator[tuple[date, date, str], None, None]:
#         """
#         按固定消息数遍历整个 Session。
#
#         一个 Chunk 可以跨越多个日期。
#
#         Yields
#         ------
#         (
#             起始日期,
#             结束日期,
#             聊天记录
#         )
#         """
#
#         if chunk_size <= 0:
#             raise ValueError("chunk_size 必须大于0。")
#
#         buffer: list[str] = []
#
#         start_date: date | None = None
#         end_date: date | None = None
#
#         for day, history in cls.iter_daily(
#                 bot_id,
#                 is_private,
#                 session_id,
#         ):
#
#             lines = history.splitlines()
#
#             if not lines:
#                 continue
#
#             if start_date is None:
#                 start_date = day
#
#             end_date = day
#
#             for line in lines:
#
#                 if not line.strip():
#                     continue
#
#                 # 当前chunk第一次加入消息
#                 if not buffer:
#                     if start_date is None:
#                         start_date = day
#
#                     end_date = day
#
#                 buffer.append(line)
#
#                 if len(buffer) >= chunk_size:
#                     yield (
#                         start_date,
#                         end_date,
#                         "\n".join(buffer),
#                     )
#
#                     buffer.clear()
#
#                     # 清空日期状态
#                     # 下一条消息重新决定开始日期
#                     start_date = None
#                     end_date = None
#         if buffer:
#             yield (
#                 start_date,
#                 end_date,
#                 "\n".join(buffer),
#             )
#
#     @classmethod
#     def iter_files(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#     ) -> Generator[tuple[date, Path], None, None]:
#         """
#         按时间顺序遍历当前 Session 的所有历史聊天文件。
#
#         Yields
#         ------
#         tuple[date, Path]
#
#             (
#                 datetime.date,
#                 txt文件路径
#             )
#         """
#
#         history_dir = cls._get_history_dir(
#             bot_id,
#             is_private,
#             session_id,
#         )
#
#         if not history_dir.exists():
#             return
#
#         for month_dir in sorted(
#                 p
#                 for p in history_dir.iterdir()
#                 if p.is_dir()
#         ):
#
#             for file in sorted(month_dir.glob("*.txt")):
#
#                 try:
#
#                     day = datetime.strptime(
#                         file.stem,
#                         "%Y-%m-%d",
#                     ).date()
#
#                 except ValueError:
#
#                     continue
#
#                 yield day, file
#
#     # ------------------------------------------------------------------
#     # Private
#     # ------------------------------------------------------------------
#
#     @staticmethod
#     def _get_session_dir(
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#     ) -> Path:
#         """
#         获取 Session 根目录。
#
#         返回：
#
#             QQ_HISTORY_DIR/
#                 bot_id/
#                     private/
#                         session_id/
#
#         或
#
#             QQ_HISTORY_DIR/
#                 bot_id/
#                     group/
#                         session_id/
#         """
#
#         session_type = "private" if is_private else "group"
#
#         return (
#                 Path(QQ_HISTORY_DIR)
#                 / str(bot_id)
#                 / session_type
#                 / str(session_id)
#         )
#
#     @classmethod
#     def _get_history_dir(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#     ) -> Path:
#         """
#         获取 llm_input 根目录。
#         """
#
#         return (
#                 cls._get_session_dir(
#                     bot_id,
#                     is_private,
#                     session_id,
#                 )
#                 / "llm_input"
#         )
#
#     @classmethod
#     def _get_history_file(
#             cls,
#             bot_id: str | int,
#             is_private: bool,
#             session_id: str | int,
#             target_date: date,
#     ) -> Path:
#         """
#         获取指定日期对应的聊天记录文件。
#         """
#
#         month = target_date.strftime("%Y-%m")
#
#         filename = target_date.strftime("%Y-%m-%d") + ".txt"
#
#         return (
#                 cls._get_history_dir(
#                     bot_id,
#                     is_private,
#                     session_id,
#                 )
#                 / month
#                 / filename
#         )
#
#     @staticmethod
#     def _read_all(
#             file_path: Path,
#     ) -> str:
#         """
#         读取整个文件。
#         """
#
#         return file_path.read_text(
#             encoding="utf-8"
#         )
#
#     @staticmethod
#     def _read_last_lines(
#             file_path: Path,
#             max_lines: int,
#     ) -> str:
#         """
#         读取最后 max_lines 行。
#         """
#
#         lines = file_path.read_text(
#             encoding="utf-8"
#         ).splitlines()
#
#         if len(lines) <= max_lines:
#             return "\n".join(lines)
#
#         return "\n".join(
#             lines[-max_lines:]
#         )


if __name__ == "__main__":

    bot_id = 1121221045
    is_private = False
    session_id = 1039857271

    print("=" * 80)
    print("最近20条")
    print("=" * 80)

    print(
        HistoryLoader.load_last(
            bot_id,
            is_private,
            session_id,
            max_lines=20,
        )
    )
    print("=" * 80)
    print("最近20条")
    print("=" * 80)

    res = HistoryLoader.load_last_list(
        bot_id,
        is_private,
        session_id,
        max_lines=20)
    for i, resi in enumerate(res):
        print(f"{i}: {resi}")

    print("=" * 80)
    print("今天聊天")
    print("=" * 80)

    print(
        HistoryLoader.load_today(
            bot_id,
            is_private,
            session_id,
        )
    )

    print("=" * 80)
    print("按天遍历")
    print("=" * 80)

    for day, history in HistoryLoader.iter_daily(
            bot_id,
            is_private,
            session_id,
    ):
        print(day, len(history.splitlines()))

    print("=" * 80)
    print("按500条切块")
    print("=" * 80)

    for index, chunk in enumerate(
            HistoryLoader.iter_chunks(
                bot_id,
                is_private,
                session_id,
                chunk_size=500,
            ),
            start=1,
    ):
        start_date, end_date, history = chunk
        print(f"Chunk {index}: {start_date} ~ {end_date}, {len(history.splitlines())} lines")

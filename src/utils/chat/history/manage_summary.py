from __future__ import annotations
from datetime import date, datetime
from pathlib import Path

from src.QQ.QQutils.resource_management.history_loader import HistoryLoader
from src.utils.chat.llm.run_prompt import PromptRunner
from src.config.path import QQ_HISTORY_DIR


class SummaryGenerator:
    """
    Summary 生成器。

    本类负责：

        1. 构造 Summary Prompt。
        2. 调用 PromptRunner。
        3. 返回 Summary。

    不负责：

        - 文件管理
        - HistoryLoader
        - Summary 更新策略
        - SummaryManager
    """

    _INITIAL_PROMPT = """
你是一名专业的信息压缩助手。
下面是一段聊天记录。
请总结其中长期有价值的信息。

要求：
1. 保留长期有效的信息。
2. 除了整理信息外，还要记录每个用户聊天的习惯、兴趣、性格等。
3. 删除寒暄、重复内容、无意义聊天。
4. 使用第三人称。
5. 不超过1000字。

仅输出摘要。
"""

    _RECENT_PROMPT = """
你是一名聊天摘要助手。
下面是最近的聊天记录。
请总结重要事件。

要求：
1. 保留这段时间发生的重要事情。
2. 除了整理信息外，还要记录每个用户聊天的习惯、兴趣、性格等。
3. 删除寒暄、重复内容、无意义聊天。
4. 使用第三人称。
5. 不超过1000字。

仅输出摘要。
"""

    _MERGE_PROMPT = """
你是一名长期记忆整理助手。
下面给出了：
旧摘要
新增摘要
请融合成为新的摘要。

要求：
1. 保留长期重要信息。
2. 除了整理信息外，还要记录每个用户聊天的习惯、兴趣、性格等。
3. 删除寒暄、重复内容、无意义聊天。
4. 使用第三人称。
5. 不超过1000字，保持内容紧凑。

仅输出新的摘要。
"""

    def __init__(
            self,
            runner: PromptRunner,
    ) -> None:
        self._runner = runner

    def generate_initial_summary(
            self,
            history: str,
    ) -> str:
        """
        根据历史聊天生成初始长期摘要。
        """

        return self._runner.run(
            system_prompt=self._INITIAL_PROMPT,
            user_prompt=history,
        )

    def generate_daily_summary(
            self,
            history: str,
    ) -> str:
        """
        根据一天聊天生成 Daily Summary。
        """

        return self._runner.run(
            system_prompt=self._RECENT_PROMPT,
            user_prompt=history,
        )

    def merge_summary(
            self,
            old_summary: str,
            new_summary: str,
    ) -> str:
        """
        融合两个摘要。

        Parameters
        ----------
        old_summary
            旧摘要。

        new_summary
            新摘要。

        Returns
        -------
        str
            融合后的摘要。
        """

        prompt = f"""旧摘要：
{old_summary}
新增摘要：
{new_summary}
"""

        return self._runner.run(
            system_prompt=self._MERGE_PROMPT,
            user_prompt=prompt,
        )


class SummaryManager:
    """
    Summary 管理器。负责维护一个 Session 的长期记忆。

    管理内容：
        summary/
            long_term.txt
            short_term.txt
            daily/
                YYYY-MM-DD.txt

    不负责：
        - Prompt设计
        - LLM调用
        - 更新触发策略

    调用关系：
        SummaryManager
            |
            +--- HistoryLoader
            |
            +--- SummaryGenerator


    """
    SUMMARY_DIR_NAME = "summary"
    LONG_TERM_FILE = "long_term.txt"
    SHORT_TERM_FILE = "short_term.txt"
    DAILY_DIR_NAME = "daily"

    def __init__(
            self,
            bot_id: str | int,
            is_private: bool,
            session_id: str | int,
            generator: SummaryGenerator,
    ) -> None:
        """
        Parameters
        ----------
        bot_id
            Bot QQ。

        is_private
            是否私聊。

        session_id
            群号或者用户QQ。

        generator
            Summary生成器。
        """

        self.bot_id = bot_id
        self.is_private = is_private
        self.session_id = session_id
        self.generator = generator
        self.summary_dir = (
                self._get_session_dir()
                / self.SUMMARY_DIR_NAME
        )
        self.daily_dir = (
                self.summary_dir
                / self.DAILY_DIR_NAME
        )
        self._ensure_dirs()

    # ============================================================
    # 初始化
    # ============================================================

    def initialize(self) -> None:
        """
        第一次初始化长期摘要。
        该方法理论上只执行一次。
        """
        # 检查long_term.txt是否存在，如果存在则不执行
        long_term_path = (self.summary_dir / self.LONG_TERM_FILE)
        if long_term_path.exists():
            print(f"长期摘要已存在，跳过初始化。路径：{long_term_path}")
            return

        long_term = ""

        for (start_date, end_date, chunk) in HistoryLoader.iter_chunks(self.bot_id, self.is_private, self.session_id):
            summary = (self.generator.generate_initial_summary(chunk))
            if not summary:
                continue
            if not long_term:
                long_term = summary
            else:
                long_term = (self.generator.merge_summary(long_term, summary))

        self._save_long_term(long_term)

    # ============================================================
    # Load
    # ============================================================

    def load_long_term(self) -> str:
        """
        读取长期摘要。
        """
        path = (self.summary_dir / self.LONG_TERM_FILE)
        if not path.exists():
            manager = SummaryManager(
                bot_id=self.bot_id,
                is_private=self.is_private,
                session_id=self.session_id,
                generator=self.generator,
            )
            manager.initialize()
        return self._read_text(path)

    def load_short_term(self) -> str:
        """
        读取短期摘要。
        """

        path = (self.summary_dir / self.SHORT_TERM_FILE)
        return self._read_text(path)

    def load_daily(self, target_date: date, ) -> str:
        """
        读取指定日期摘要。
        """

        path = (self.daily_dir / f"{target_date.strftime('%Y-%m-%d')}.txt")

        return self._read_text(path)

    # ============================================================
    # Save
    # ============================================================

    def _save_long_term(self, content: str, ) -> None:
        """
        保存长期摘要。
        """
        self._write_text(self.summary_dir / self.LONG_TERM_FILE, content)

    def _save_short_term(self, content: str, ) -> None:
        """
        保存短期摘要。
        """

        self._write_text(self.summary_dir / self.SHORT_TERM_FILE, content, )

    def _save_daily(self, target_date: date, content: str) -> None:
        """
        保存每日摘要。
        """
        path = (self.daily_dir / f"{target_date.strftime('%Y-%m-%d')}.txt")
        self._write_text(path, content)

    # ============================================================
    # Path
    # ============================================================

    def _get_session_dir(self) -> Path:
        """
        获取当前Session目录。

        返回：

            QQ_HISTORY_DIR/
                bot/
                    private/group/
                        session
        """
        session_type = ("private" if self.is_private else "group")
        return Path(QQ_HISTORY_DIR) / str(self.bot_id) / session_type / str(self.session_id)

    def _ensure_dirs(self) -> None:
        """
        创建summary目录。
        """

        self.summary_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # File IO
    # ============================================================

    @staticmethod
    def _read_text(path: Path) -> str:
        """
        读取文本文件。
        """
        if not path.exists():
            return ""
        return path.read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        """
        写入文本文件。
        """
        path.write_text(content.strip(), encoding="utf-8")

    # ============================================================
    # Update Short Term
    # ============================================================

    def update_short_term(
            self,
            recent_history: str,
    ) -> None:
        """
        更新短期摘要。
        调用时机：
            外部控制，例如：
                每50条消息一次
        Parameters
        ----------
        recent_history
            最近一段聊天记录。
        """

        old_summary = (
            self.load_short_term()
        )

        # 第一次生成short summary
        if not old_summary:

            new_summary = (
                self.generator
                .generate_daily_summary(
                    recent_history
                )
            )

        else:

            new_summary = (
                self.generator
                .merge_summary(
                    old_summary,
                    recent_history,
                )
            )

        if new_summary:
            self._save_short_term(
                new_summary
            )

    # ============================================================
    # Update Daily
    # ============================================================

    def update_daily(
            self,
            target_date: date | None = None,
    ) -> None:
        """
        生成某一天的 Daily Summary。
        Parameters
        ----------
        target_date

            默认为今天。

        """

        if target_date is None:
            target_date = datetime.now().date()

        history = (
            HistoryLoader.load_date(
                self.bot_id,
                self.is_private,
                self.session_id,
                target_date,
            )
        )

        if not history:
            return

        summary = (
            self.generator
            .generate_daily_summary(
                history
            )
        )

        if summary:
            self._save_daily(
                target_date,
                summary,
            )

    # ============================================================
    # Update Long Term
    # ============================================================

    def update_long_term(
            self,
            target_date: date | None = None,
    ) -> None:
        """
        使用 Daily Summary 更新长期摘要。
        注意：
            这里不读取聊天记录。
            因为每日聊天已经压缩成daily summary。
        """

        if target_date is None:
            target_date = datetime.now().date()

        daily_summary = (
            self.load_daily(
                target_date
            )
        )

        if not daily_summary:
            return

        old_long_term = (
            self.load_long_term()
        )

        if not old_long_term:

            new_long_term = daily_summary

        else:

            new_long_term = (
                self.generator
                .merge_summary(
                    old_long_term,
                    daily_summary,
                )
            )

        if new_long_term:
            self._save_long_term(
                new_long_term
            )

    # ============================================================
    # Rebuild
    # ============================================================

    def rebuild_long_term(self) -> None:
        """
        根据所有 daily summary 重新构建 long_term。

        使用场景：

            - 修改了 Summary Prompt
            - 修改了总结策略
            - long_term 出错
        """

        long_term = ""

        daily_files = sorted(
            self.daily_dir.glob(
                "*.txt"
            )
        )

        for file in daily_files:

            daily_summary = (
                self._read_text(
                    file
                )
            )

            if not daily_summary:
                continue

            if not long_term:
                long_term = daily_summary
            else:
                long_term = (
                    self.generator
                    .merge_summary(
                        long_term,
                        daily_summary,
                    )
                )

        self._save_long_term(
            long_term
        )


if __name__ == "__main__":
    bot_id = 1121221045
    is_private = False
    session_id = 1039857271
    runner = PromptRunner()
    generator = SummaryGenerator(
        runner
    )
    manager = SummaryManager(
        bot_id=bot_id,
        is_private=is_private,
        session_id=session_id,
        generator=generator,
    )

    # =====================================================
    # 第一次初始化
    # =====================================================

    manager.initialize()

    # =====================================================
    # 更新短期记忆
    # =====================================================

    history = HistoryLoader.load_last(
        bot_id,
        is_private,
        session_id,
        max_lines=50,
    )

    manager.update_short_term(
        history
    )

    # =====================================================
    # 生成当天摘要
    # =====================================================

    manager.update_daily()

    # =====================================================
    # 更新长期摘要
    # =====================================================

    manager.update_long_term()

    print(
        "long_term:"
    )

    print(
        manager.load_long_term()
    )

    print(
        "\nshort_term:"
    )

    print(
        manager.load_short_term()
    )

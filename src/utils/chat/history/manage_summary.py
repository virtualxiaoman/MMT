from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
import json

from src.QQ.QQutils.res.history_loader import HistoryLoader
from src.utils.chat.llm.run_prompt import PromptRunner
from src.config.path import QQ_HISTORY_DIR, PROMPT_DIR
from src.utils.tools.file import load_from_txt


class SummaryGenerator:
    """
    Summary 生成器。
    本类负责：
        1. 构造 Summary Prompt。
        2. 调用 PromptRunner。
        3. 返回 Summary。
    """
    _INITIAL_PROMPT = load_from_txt(Path(PROMPT_DIR) / "tools/summary/initial.txt")
    _RECENT_PROMPT = load_from_txt(Path(PROMPT_DIR) / "tools/summary/recent.txt")
    _MERGE_PROMPT = load_from_txt(Path(PROMPT_DIR) / "tools/summary/merge.txt")

    def __init__(self, runner: PromptRunner) -> None:
        self._runner = runner

    def generate_initial_summary(self, history: str) -> str:
        """
        根据历史聊天生成初始长期摘要。
        """
        return self._runner.run(system_prompt=self._INITIAL_PROMPT, user_prompt=history)

    def generate_recent_summary(self, history: str) -> str:
        """
        根据最近的聊天生成 Summary。
        """
        return self._runner.run(system_prompt=self._RECENT_PROMPT, user_prompt=history)

    def merge_summary(self, old_summary: str, new_summary: str) -> str:
        """
        融合两个摘要。

        Parameters
        ----------
        old_summary: 旧摘要。
        new_summary: 新摘要。

        Returns
        -------
        str: 融合后的摘要。
        """
        prompt = f"""旧摘要：\n{old_summary}\n新增摘要：\n{new_summary}"""
        return self._runner.run(system_prompt=self._MERGE_PROMPT, user_prompt=prompt)


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
    METADATA_FILE = "metadata.json"
    SHORT_INTERVAL = 50

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

        self.summary_dir = self._get_session_dir() / self.SUMMARY_DIR_NAME
        self.daily_dir = self.summary_dir / self.DAILY_DIR_NAME
        self.metadata_path = self.summary_dir / self.METADATA_FILE
        print(f"metadata_path={self.metadata_path}")

        self._ensure_dirs()
        self._init_metadata()

    # ============================================================
    # 初始化
    # ============================================================

    def initialize_long_term(self) -> None:
        """
        第一次初始化长期摘要。
        该方法理论上每个文件只会执行一次。
        """
        # 检查long_term.txt是否存在，如果存在则不执行
        long_term_path = self.summary_dir / self.LONG_TERM_FILE
        if long_term_path.exists():
            print(f"长期摘要已存在，跳过初始化。路径：{long_term_path}")
            return

        self._save_long_term("长期记忆暂无内容")  # 暂时保存以防止多次调用反复生成
        long_term = ""
        chunks = list(HistoryLoader.iter_chunks(self.bot_id, self.is_private, self.session_id))
        for i, (start_date, end_date, chunk) in enumerate(chunks, 1):
            print(f"[{i}/{len(chunks)}] 正在总结 {start_date} ~ {end_date}")
            summary = self.generator.generate_initial_summary(chunk)
            if not summary:
                continue
            if not long_term:
                long_term = summary
            else:
                long_term = (self.generator.merge_summary(long_term, summary))
                self._save_long_term(long_term)  # 暂时保存以防止丢失

        self._save_long_term(long_term)

    def initialize_short_term(self, recent_history: str | None = None) -> None:
        if recent_history is None:
            recent_history = HistoryLoader.load_last(self.bot_id, self.is_private, self.session_id, max_lines=50)
        new_summary = self.generator.generate_recent_summary(recent_history)
        self._save_short_term(new_summary)

    # ============================================================
    # Update Short Term
    # ============================================================
    def update_short_term(self, recent_history: str | None = None) -> None:
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
        if recent_history is None:
            recent_history = HistoryLoader.load_last(self.bot_id, self.is_private, self.session_id, max_lines=100)
        old_summary = self.load_short_term()
        # 第一次生成short summary
        if not old_summary:
            new_summary = self.generator.generate_recent_summary(recent_history)
        else:
            new_summary = self.generator.merge_summary(old_summary, recent_history)
        if new_summary:
            self._save_short_term(new_summary)
            print("[update_short_term] 更新recent_history完成")

    # ============================================================
    # Update Daily
    # ============================================================
    def update_daily(self, target_date: date | None = None) -> None:
        """
        生成某一天的 Daily Summary。
        Parameters
        ----------
        target_date
            默认为今天。
        """
        if target_date is None:
            target_date = datetime.now().date()
        history = HistoryLoader.load_date(self.bot_id, self.is_private, self.session_id, target_date)
        if not history:
            return
        summary = self.generator.generate_recent_summary(history)
        if summary:
            self._save_daily(target_date, summary)
            print(f"[update_daily] 更新{target_date}完成")

    # ============================================================
    # Update Long Term
    # ============================================================
    def update_long_term(self, target_date: date | None = None) -> None:
        """
        使用 Daily Summary 更新长期摘要。
        注意：
            这里不读取聊天记录。
            因为每日聊天已经压缩成daily summary。
        """

        if target_date is None:
            target_date = datetime.now().date()
        daily_summary = self.load_daily(target_date)

        if not daily_summary:
            return

        old_long_term = self.load_long_term()
        if not old_long_term:
            new_long_term = daily_summary
        else:
            new_long_term = self.generator.merge_summary(old_long_term, daily_summary)
        if new_long_term:
            self._save_long_term(new_long_term)
            print(f"[update_long_term] 更新{target_date}完成")

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
        daily_files = sorted(self.daily_dir.glob("*.txt"))

        for file in daily_files:
            daily_summary = (self._read_text(file))
            if not daily_summary:
                continue
            if not long_term:
                long_term = daily_summary
            else:
                long_term = (self.generator.merge_summary(long_term, daily_summary))

        self._save_long_term(long_term)
        print(f"[rebuild_long_term] 更新完成")

    # ============================================================
    # Load
    # ============================================================

    def load_long_term(self) -> str:
        """
        读取长期摘要。
        """
        path = self.summary_dir / self.LONG_TERM_FILE
        if not path.exists():
            self.initialize_long_term()
        return self._read_text(path)

    def load_short_term(self) -> str:
        """
        读取短期摘要。
        """
        path = self.summary_dir / self.SHORT_TERM_FILE
        if not path.exists():
            self.initialize_short_term()
        return self._read_text(path)

    def load_daily(self, target_date: date, ) -> str:
        """
        读取指定日期摘要。
        """
        path = self.daily_dir / f"{target_date.strftime('%Y-%m-%d')}.txt"
        result = self._read_text(path)
        if result:
            return result
        else:
            print(f"[load_daily] {target_date}无数据，正在重新生成")
            self.update_daily(target_date)
            self.load_daily(target_date)

    def sync(self) -> None:
        """
        同步所有Summary。

        调用时机：
            每次聊天结束后调用一次。
        """
        print("_sync_short_term")
        self._sync_short_term()
        print("_sync_daily")
        self._sync_daily()
        print("_sync_long_term")
        self._sync_long_term()

    # ============================================================
    # Short Term
    # ============================================================

    def _sync_short_term(self) -> None:
        today = datetime.now().date()
        current_count = self._get_message_count()
        metadata = self._load_metadata()
        last_date = metadata.get(
            "short_last_date"
        )
        last_count = metadata.get(
            "last_short_message_count",
            0,
        )
        if last_date != str(today):
            print(f"last_date={last_date}, today={today}")
            last_count = 0
        if current_count - last_count < self.SHORT_INTERVAL:
            return

        history = HistoryLoader.load_today_range(
            self.bot_id,
            self.is_private,
            self.session_id,
            start=last_count,
            end=current_count,
        )
        old_summary = self.load_short_term()

        if old_summary:
            summary = self.generator.merge_summary(
                old_summary,
                history,
            )
        else:
            summary = self.generator.generate_recent_summary(history)

        if summary:
            self._save_short_term(summary)
            metadata["short_last_date"] = str(today)
            metadata["last_short_message_count"] = current_count
            self._save_metadata(metadata)
        else:
            print("[_sync_short_term] summary生成失败")

    # ============================================================
    # Daily
    # ============================================================

    def _sync_daily(self) -> None:
        metadata = self._load_metadata()
        last_date = metadata.get(
            "last_daily_date"
        )
        if last_date:
            last_date = date.fromisoformat(last_date)
        else:
            last_date = HistoryLoader.get_first_date(bot_id=self.bot_id, session_id=self.session_id,
                                                     is_private=self.is_private)
            if last_date is None:
                return

        yesterday = datetime.now().date() - timedelta(days=1)

        while last_date < yesterday:
            target = last_date + timedelta(days=1)

            self.update_daily(target)

            last_date = target

            metadata["last_daily_date"] = (
                target.isoformat()
            )

            self._save_metadata(metadata)

    # ============================================================
    # Long Term
    # ============================================================

    def _sync_long_term(self) -> None:

        metadata = self._load_metadata()

        last_date = metadata.get(
            "last_long_date"
        )

        if last_date:
            last_date = date.fromisoformat(last_date)
        else:
            last_date = HistoryLoader.get_first_date(bot_id=self.bot_id, session_id=self.session_id,
                                                     is_private=self.is_private)
            if last_date is None:
                return

        daily_dates = sorted(
            self.daily_dir.glob("*.txt")
        )

        for file in daily_dates:

            current = date.fromisoformat(
                file.stem
            )

            if current <= last_date:
                continue

            daily_summary = self._read_text(file)

            if not daily_summary:
                continue

            old = self.load_long_term()

            if old:
                new = self.generator.merge_summary(
                    old,
                    daily_summary,
                )
            else:
                new = daily_summary

            if new:
                self._save_long_term(new)  # 确保融合后有实质内容再覆盖保存

                metadata["last_long_date"] = (
                    current.isoformat()
                )

                self._save_metadata(metadata)

    # ============================================================
    # Metadata
    # ============================================================

    def _init_metadata(self):

        if self.metadata_path.exists():
            return

        self._save_metadata(
            {
                "last_short_message_count": 0,
                "short_last_date": None,
                "last_daily_date": None,
                "last_long_date": None,
            }
        )

    def _load_metadata(self) -> dict:

        if not self.metadata_path.exists():
            self._init_metadata()

        return json.loads(
            self.metadata_path.read_text(
                encoding="utf-8"
            )
        )

    def _save_metadata(
            self,
            data: dict,
    ) -> None:

        self.metadata_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

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
    # Utils
    # ============================================================
    def _get_message_count(self) -> int:
        """
        获取当前Session消息数量。

        建议直接从HistoryLogger metadata读取，
        不要每次扫描文件。
        """

        return HistoryLoader.count_today(
            self.bot_id,
            self.is_private,
            self.session_id,
        )

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
        print(f"正在读取{path}")
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        """
        写入文本文件。
        """
        path.write_text(content.strip(), encoding="utf-8")


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

    manager.initialize_long_term()

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

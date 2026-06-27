from __future__ import annotations

import json
import os
import pickle
from datetime import datetime
from pathlib import Path

from src.QQ.QQutils.msg.msg_wrapper import MessageWrapper
from src.config.path import HISTORY_DIR


class HistoryLogger:
    """
    聊天记录持久化

    目录结构：

    HISTORY_DIR/
        qq_chat/
            bot_id/
                private/
                    user_id/
                        raw/
                            2026-06/
                                2026-06-27.pkl
                        canonical/
                            2026-06/
                                2026-06-27.jsonl
                        llm_input/
                            2026-06/
                                2026-06-27.txt
                        human/
                            2026-06/
                                2026-06-27.md

                group/
                    group_id/
                        ...
    """

    def __init__(self, config):
        self.bot_id = str(config.qq_id)
        self.root = Path(HISTORY_DIR) / "qq_chat" / self.bot_id

    # ==========================================================
    # 对外接口
    # ==========================================================

    def append(self, msg, message_wrapper: MessageWrapper):
        """
        追加一条聊天记录

        Parameters
        ----------
        msg
            原始消息对象
        message_wrapper
            标准化消息
        """

        self._append_raw(msg, message_wrapper)
        self._append_canonical(message_wrapper)
        self._append_llm_input(message_wrapper)
        self._append_human(message_wrapper)

    # ==========================================================
    # 路径
    # ==========================================================

    def _session_dir(self, wrapper: MessageWrapper) -> Path:
        """
        获取当前会话目录
        """

        session_type = "private" if wrapper.is_private else "group"

        return (
                self.root
                / session_type
                / str(wrapper.session_id)
        )

    def _month_str(self, wrapper: MessageWrapper) -> str:
        return datetime.fromtimestamp(
            wrapper.timestamp
        ).strftime("%Y-%m")

    def _day_str(self, wrapper: MessageWrapper) -> str:
        return datetime.fromtimestamp(
            wrapper.timestamp
        ).strftime("%Y-%m-%d")

    def _build_file(
            self,
            wrapper: MessageWrapper,
            category: str,
            suffix: str
    ) -> Path:
        """
        构造文件路径

        例如：

        canonical/
            2026-06/
                2026-06-27.jsonl
        """

        folder = (
                self._session_dir(wrapper)
                / category
                / self._month_str(wrapper)
        )

        folder.mkdir(
            parents=True,
            exist_ok=True
        )

        return folder / f"{self._day_str(wrapper)}.{suffix}"

    # ==========================================================
    # raw
    # ==========================================================

    def _append_raw(
            self,
            msg,
            wrapper: MessageWrapper
    ):
        """
        原始消息

        pickle连续dump
        """

        path = self._build_file(
            wrapper,
            "raw",
            "pkl"
        )

        with path.open("ab") as f:
            pickle.dump(
                msg,
                f,
                protocol=pickle.HIGHEST_PROTOCOL
            )

    # ==========================================================
    # canonical
    # ==========================================================

    def _append_canonical(
            self,
            wrapper: MessageWrapper
    ):
        """
        标准化消息

        jsonl
        """

        path = self._build_file(
            wrapper,
            "canonical",
            "jsonl"
        )

        with path.open(
                "a",
                encoding="utf-8"
        ) as f:
            json.dump(
                wrapper.json,
                f,
                ensure_ascii=False
            )

            f.write("\n")

    # ==========================================================
    # llm_input
    # ==========================================================

    def _append_llm_input(
            self,
            wrapper: MessageWrapper
    ):
        """
        LLM输入文本
        """

        path = self._build_file(
            wrapper,
            "llm_input",
            "txt"
        )

        with path.open(
                "a",
                encoding="utf-8"
        ) as f:
            f.write(wrapper.text_msg)
            f.write("\n")

    # ==========================================================
    # human
    # ==========================================================

    def _append_human(
            self,
            wrapper: MessageWrapper
    ):
        """
        人类阅读版

        第二部分实现
        """
        path = self._build_file(
            wrapper,
            "human",
            "md"
        )

        markdown = self._build_human_markdown(
            wrapper
        )

        with path.open(
                "a",
                encoding="utf-8"
        ) as f:
            f.write(markdown)
            f.write("\n\n")

    # ==========================================================
    # Human Markdown
    # ==========================================================

    def _build_human_markdown(
            self,
            wrapper: MessageWrapper
    ) -> str:
        """
        构造人类阅读版 Markdown（HTML增强）
        """

        time_str = datetime.fromtimestamp(
            wrapper.timestamp
        ).strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"### {time_str}　**{wrapper.user_nickname}**",
            ""
        ]

        for seg in wrapper.segments:

            seg_type = seg["type"]

            # --------------------------------------------------
            # 文本
            # --------------------------------------------------
            if seg_type == "text":

                text = (
                    seg["content"].strip()
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>")
                )

                lines.append(
                    f"""
    <div style="
    display:inline-block;
    background-color: rgba(102, 204, 255, 0.2);
    color:#1F2937;
    padding:8px 12px;
    border-radius:12px;
    max-width:75%;
    line-height:1.6;
    margin:6px 0;
    word-break:break-word;
    ">
    {text}
    </div>
    """.strip()
                )

            # --------------------------------------------------
            # @
            # --------------------------------------------------
            elif seg_type == "at":

                lines.append(
                    f"""
    <div style="
    display:inline-block;
    background-color: rgbA(255, 248, 220, 0.8);
    color:#1F2937;
    padding:8px 12px;
    border-radius:12px;
    margin:6px 0;
    ">
    @{seg["qq_id"]}
    </div>
    """.strip()
                )

            # --------------------------------------------------
            # QQ系统表情
            # --------------------------------------------------
            elif seg_type == "qq_face":

                content = seg.get("content") or "[QQ表情]"

                lines.append(
                    f"""
    <div style="
    display:inline-block;
    background-color: rgba(102, 204, 255, 0.2);
    color:#1F2937;
    padding:8px 12px;
    border-radius:12px;
    max-width:75%;
    line-height:1.6;
    margin:6px 0;
    ">
    {content}
    </div>
    """.strip()
                )

            # --------------------------------------------------
            # 图片
            # --------------------------------------------------
            elif seg_type in ("image", "qq_emoji"):

                file = seg.get("file")

                if file:

                    file = self._human_relative_file(
                        wrapper,
                        file
                    )

                    if seg_type == "image":
                        lines.append(
                            f"""
<img src="{file}"
style="
max-width:250px;
width:auto;
height:auto;
margin:8px 0;
display:block;
">
""".strip()
                        )
                    elif seg_type == "qq_emoji":
                        lines.append(
                            f"""
<img src="{file}"
style="
max-width:150px;
width:auto;
height:auto;
margin:8px 0;
display:block;
">
""".strip()
                        )

                else:

                    lines.append(
                        """
    <div style="
    display:inline-block;
    background:#66CCFF;
    color:#1F2937;
    padding:12px 16px;
    border-radius:16px;
    margin:6px 0;
    ">
    [图片]
    </div>
    """.strip()
                    )

            # --------------------------------------------------
            # 未知类型
            # --------------------------------------------------
            else:

                lines.append(
                    f"""
    <div style="
    display:inline-block;
    background:#EEEEEE;
    color:#666666;
    padding:10px 14px;
    border-radius:12px;
    margin:6px 0;
    ">
    未知消息类型：{seg_type}
    </div>
    """.strip()
                )

        lines.append("")

        return "\n".join(lines)

    def _human_relative_file(
            self,
            wrapper: MessageWrapper,
            file: str
    ) -> str:
        """
        返回 markdown 到图片的相对路径
        """

        md_dir = self._build_file(
            wrapper,
            "human",
            "md"
        ).parent

        image_path = self.root / file

        return os.path.relpath(
            image_path,
            md_dir
        ).replace("\\", "/")

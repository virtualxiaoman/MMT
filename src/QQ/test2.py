from pathlib import Path
import asyncio
import logging
from typing import Dict

from ncatbot.core import BotClient, GroupMessage
from src.utils.chat import ChatDSAPI
from src.utils.decider import ReplyDecider


# todo https://github.com/liyihao1110/ncatbot/issues/231


# ========== 1. 创建 BotClient ==========
bot = BotClient()

# ========== 2. 创建一个字典，用来存储不同群的“独立记忆大脑” ==========
# 格式类似： { 群号1: ChatDSAPI实例1, 群号2: ChatDSAPI实例2 }
chat_sessions = {}
should_reply_sessions = {}


# ========== 3. 注册群聊回调函数 ==========
@bot.group_event()
async def on_group_message(msg: GroupMessage):
    print(f"收到群【{msg.group_id}】中用户【{msg.user_id}】的消息: {msg.raw_message}")

    user_text = msg.raw_message.strip()
    # if not real_query:
    #     await bot.api.post_group_msg(group_id=msg.group_id, text="在呢！有什么可以帮你的喵？")
    #     return
    # print(f"正在交给 AI 处理: {real_query}")

    # 核心修改：为每个群聊分配独立的 AI 实例，确保记忆不串线
    session_id = msg.group_id  # 这里以群号为单位隔离记忆。如果想按人隔离，可以用 msg.user_id

    # 如果这个群是第一次呼叫白子
    if session_id not in chat_sessions:
        print(f"正在为群 {session_id} 初始化专属 AI 记忆...")
        chat_sessions[session_id] = ChatDSAPI()
        chat_sessions[session_id].init_role("砂狼白子")
        should_reply_sessions[session_id] = ReplyDecider(name="白子", qq_id=1291606697)

    should_reply = should_reply_sessions[session_id].check_if_should_reply(user_text)
    if should_reply:
        # 只要代码不重启，这个实例的 self.msg 就会一直保留，自动实现多轮记忆
        ai_reply = chat_sessions[session_id].one_chat(user_text)
        await bot.api.post_group_msg(group_id=msg.group_id, text=ai_reply)  # 将回复发送到群聊
    else:
        print(f"决定不回复这条消息: {user_text}")


if __name__ == "__main__":
    bot.run()

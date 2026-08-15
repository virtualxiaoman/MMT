# MMT 代码审查报告

## 审查范围与结论

审查范围：`src/QQ/QQutils`、`src/utils/chat`、`src/config`、`src/utils/tools`、入口文件与相关配置。按你的要求排除了 `src/QQ/napcat`、`src/QQ/logs`、`src/QQ/data`、`QQBot_Shiroko.py`、各类测试文件，以及 `assets/history` 的具体消息内容。

总体结论：项目功能雏形完整，但当前代码存在几类系统性问题，建议先处理 P0/P1：

- Tavily API Key 曾硬编码并提交，已从当前工作区移除，仍需确认是否吊销。
- AI 回复的上下文构建逻辑实际会丢掉大部分历史，隐式回读本身也较脆弱。
- 图片消息会被重复下载，且 `EmojiDetector` 存在连接与文件句柄泄漏。
- 会话、LLM、Summary 对象在每次回复时被反复重建，成本高且状态难以复用。

## 修复记录（2026-08-15）

- 移除 `llm_search.py` 中的硬编码 Tavily Key，改为 `TAVILY_API_KEY` 环境变量注入，并去掉模块导入副作用。
- 修复 `ConversationManager` 的清空语义：构造上下文时不再因 `enable_memory=False` 丢掉历史；`ChatPipeline` 增加当前消息兜底。
- `ChatSession` 改为复用 `ChatPipeline/SummaryManager`，不再每次回复重建 LLM 对象。
- `ChatPipeline` 改为读取 canonical JSONL 结构化历史，支持跨天最近消息；发送消息也写入 canonical。
- 图片处理改为先落盘再描述/检测，`EmojiDetector` 与 `ImageDescriber` 改为 BotManager 共享实例；表情目录读取 bot YAML。
- 修复 `SummaryManager.load_daily()` 无限递归、`HistoryLoader.load_today_range()` 返回 `None`、跨盘符历史相对路径报错。
- 群聊 ACL 增加发送者用户黑名单校验；`BanCommand` 无单位时按分钟处理。
- `LyricRepository` 改为启动时建索引并过滤单字；`RandomPicture` 空库返回 `None`。
- `ReplyScheduler` 在回调执行期间到达的新消息会重新开一轮；`VoiceDecider` 增加缓存校验和零向量保护。
- 删除 `history_loader.py`、`QQ_reply_settings.py`、`specify_lyric.py`、`specify_music.py` 中的大段旧实现死代码。

## P0 阻断与安全

### 1. 硬编码 Tavily API Key 曾提交进仓库

原 `src/utils/chat/search/llm_search.py` 中写有真实格式的 Tavily Key，且模块顶层会直接执行搜索请求；只要有人 import 该模块就会产生外部网络调用。该 Key 已从当前工作区移除，`llm_search.py` 改为通过环境变量 `TAVILY_API_KEY` 注入，并把搜索逻辑放进 `search_web()`，仅在 `if __name__ == "__main__"` 中演示调用。

由于 Key 已经进入过 Git 历史（至少存在于提交 `4e4e3f0`），仅删除工作区文件内容不等于彻底清除历史；如果该 Key 曾对外暴露，仍建议在 Tavily 后台吊销或轮换。

## P1 高优先级问题

### 2. `ChatPipeline` 依赖隐式历史回读，且历史被 `enable_memory=False` 清空

`src/QQ/QQutils/msg/pipeline.py:91-99` 没有显式调用 `conv.add_user(user_query)`，当前回复依赖“先由 `HistoryLogger` 写入本地、再让 `_append_history()` 从本地读回当前消息”的隐式流程。按你的说明这是有意的，但这个隐式链路要求历史写入必须严格先于上下文构造，且只读当天文本文件，仍然脆弱。

```python
conv = ConversationManager(system_prompt=system_prompt, enable_memory=False)
self._append_history(conv=conv)
reply = self.llm.one_chat(conv.messages)
```

更严重的是 `ConversationManager(enable_memory=False)` 的语义。`src/utils/chat/manager/conversation.py:60-71` 中每次 `add_user()` 都会 `_reset()`，`107-121` 中 `add_assistant()` 直接返回。实测：

```text
add_user("u1"); add_user("u2"); add_assistant("a1")
=> [system, {"role": "user", "content": "u2"}]
```

也就是说，即便 `_append_history()` 逐条读入历史，最终发给 LLM 的也只有最后一条 user 消息，所有 assistant 回复和更早上下文全部丢失。建议：

- 若保留隐式回读，至少在构造消息前确认当前消息已成功落盘；更稳妥是在 `ChatPipeline` 中显式接收当前用户消息。
- 使用 `canonical` JSONL 或结构化消息对象构造上下文，而不是重新解析文本。
- 移除 `enable_memory=False` 这种“重置式”用法，或重新设计 `ConversationManager` 的语义。

### 3. 每次回复都重建 LLM、Summary、Pipeline，成本和状态管理失控

`src/QQ/QQutils/msg/chat_session.py:190-204` 的 `chat_pipeline()` 每次回复都创建 `PromptRunner`、`SummaryGenerator`、`SummaryManager`、`ChatPipeline`，而 `ChatPipeline` 内部又创建 `LLMDSAPI` 与 `ConversationManager`。

`SummaryManager.sync()` 还会在每次聊天后尝试补齐短时摘要、日报和长期摘要（`src/utils/chat/history/manage_summary.py:296-308`）。首次运行或补历史时，这可能变成一次回复几十次 LLM 调用。建议：

- 每个 `ChatSession` 持有一个可复用的 `ChatPipeline`/`SummaryManager`/LLM client。
- 摘要同步改为定时任务或消息计数触发，不要在回复热路径中同步执行。

### 4. 图片消息被重复下载，且 `EmojiDetector` 资源泄漏

一条图片消息的处理链至少发生三次网络下载：

1. `RecvMessageWrapper.fill_image_content()` 创建 `ImageDescriber` 并下载图片做 VLM 描述：`src/QQ/QQutils/msg/msg_wrapper.py:119-140`、`src/utils/chat/img_describer.py:105-113`。
2. `ImageStorage.process()` 再次下载同一 URL 并保存：`src/QQ/QQutils/res/image_storage.py:96-109, 284-319`。
3. `_should_reply()` 对单图调用 `EmojiDetector.is_emoji()`，第三次下载：`src/QQ/QQutils/msg/chat_session.py:164-174`、`src/utils/tools/res/emoji_detector.py:69-77`。

`RecvMessageWrapper` 每条消息都会创建新的 `ImageDescriber` 和 `EmojiDetector`（`src/QQ/QQutils/msg/msg_wrapper.py:25-28`），而 `EmojiDetector` 持有 SQLite 连接和 `requests.Session`，正常流程没有 `close()`。`ChatSession` 里还有另一个长期不释放的 `EmojiDetector`（`src/QQ/QQutils/msg/chat_session.py:58-60`）。建议：

- 图片下载只发生一次，下载后本地文件同时用于保存、哈希、VLM 描述和表情检测。
- `EmojiDetector` 改为进程级单例或随 `BotManager` 生命周期管理，并提供关闭钩子。
- 两处硬编码的 `D:\Users\Administrator\Desktop\Emoji\LuoTianyi` 暂时保留，但改为写入 bot 的 YAML 配置并由 `BotConfig` 注入，避免继续散落在 `msg_wrapper.py` 和 `chat_session.py`；后续再迁移到 `assets/emoji/<role>`。

### 5. 历史以 `llm_input.txt` 文本为主数据源，解析脆弱且跨天上下文丢失

`HistoryLoader.load_last_list()` 只读取今天的 `llm_input/*.txt`（`src/QQ/QQutils/res/history_loader.py:99-110`），但它被用于回复决策和聊天上下文。跨天对话会失去昨天上下文。

`ChatPipeline._append_history()` 再用字符串解析判断发言人：

```python
prefix, content = msg.split("：", 1)
_, speaker = prefix.split("] ", 1)
```

这依赖昵称、时间格式和分隔符永远稳定。项目已经写了结构化 `canonical/*.jsonl`，但聊天链路没有使用它。建议统一以 canonical JSONL 为事实来源，文本文件只用于人工阅读或导出。

### 6. 发送消息的历史存储缺少 canonical/raw，数据模型不对称

`HistoryLogger.append_send()` 只写 `llm_input` 和 `human`，不写 `canonical` 与 `raw`（`src/QQ/QQutils/res/history_storage.py:68-80`）。结果是机器人回复无法从结构化历史中查询，只能从文本中猜。建议让收发消息走同一套存储协议，发送消息至少写入 canonical，raw 可根据需要忽略。

### 7. `ChatDSAPI` 硬编码模型名，模型配置没有真正生效

`src/utils/chat/role_chat.py:123-137` 先根据 `model_settings` 选模型，然后无条件覆盖：

```python
self.model_name = "deepseek-v4-pro"  # todo: 这里直接写死
```

同时项目里存在 `ChatDSAPI`、`LLMDSAPI`、`DeepSeekClient` 三套几乎重复的 OpenAI 封装。`models.yaml` 中的 `reply_model`、`decide_model`、`emoji_model` 没有被统一消费。建议：

- 收敛到单一 LLM 封装，模型名从配置注入。
- 删除未生效的本地模型分支和 todo 硬编码。

### 8. `SummaryManager.load_daily()` 存在无限递归

`src/utils/chat/history/manage_summary.py:283-294`：

```python
if result:
    return result
else:
    self.update_daily(target_date)
    self.load_daily(target_date)
```

如果 `update_daily()` 因“当天没有聊天记录”直接 `return` 而不写文件，这里会无限递归直到栈溢出。应改为“生成一次后再次判断，仍为空就返回空字符串”。

## P2 中优先级问题

### 9. 群聊权限只按群号判断，无法按用户黑名单拒绝

`QQBot_LuoTianyi._can_reply()` 只传 `session_id`（群号）给 `QQReplySettings.can_reply()`（`src/QQ/QQBot_LuoTianyi.py:159-166`），因此 `QQ_reply_settings.py:424-433` 在群聊中只检查群号，不检查发送者 QQ。配置里的 `black_private` 用户黑名单只对私聊生效。建议 `can_reply()` 同时接收 `user_id` 和 `group_id`，群聊分别校验用户与群。

### 10. `BanCommand` 在“禁言时长没有单位”时会 KeyError

`src/QQ/QQutils/cmds/commands.py:394-414` 的正则允许 `#禁言 @123 3`，此时 `m.group(3)` 为 `None`，随后执行 `TIME_UNITS[unit]` 会抛 `KeyError`。实测：

```text
groups = ("123", "3", None)
```

建议要么强制单位，要么无单位时使用默认分钟。

### 11. `LyricCommand` 每条消息都会全量扫描歌词库

`src/QQ/QQutils/cmds/commands.py:212-213`：

```python
def match(self, text: str) -> bool:
    return True
```

`match()` 恒为 True 是“直接匹配”的预期设计。问题不在没有显式关键词，而在每条消息都会进入 `LyricRepository.find_next_line()`，同步递归扫描所有歌词文件（`src/utils/tools/res/specify_lyric.py:55-80`）。建议：

- 保留直接匹配，但歌词库启动时建立索引，不要每次消息都全盘扫描。
- 过滤单字输入，避免“啊”这类语气词命中并拦截正常聊天。

### 12. `RandomPicture` 无图时返回错误字符串而不是失败信号

`src/utils/tools/res/rand_pic.py:38-43` 在图片库为空时返回：

```python
return "未在指定目录及其子目录中找到任何图片文件。"
```

`ImageCommand` 随后把该字符串当图片路径发送，会触发 QQ API 错误。建议返回 `None` 或抛异常，由命令层发提示文本。

### 13. `ReplyScheduler` 只保存最新 ctx，回复期间新消息会计数丢失

`src/utils/chat/reply_scheduler.py:57-100` 只保存 `latest_ctx`，`pending_count` 在回调结束后无条件清零。若回调执行期间又来了新消息，这些消息不会获得新的调度任务。建议维护一个小型待回复队列，或至少在 `finally` 中判断 `pending_count` 是否大于已处理批次。

### 14. `HistoryLoader.load_today_range()` 类型与返回不一致

`src/QQ/QQutils/res/history_loader.py:409-428` 在 `start >= end` 时返回 `None`，但函数声明和正常路径都返回 `str`。调用方 `SummaryManager._sync_short_term()` 可能把 `None` 传给 LLM。建议统一返回空字符串或抛参数错误。

### 15. `EmojiDetector` 的 SQLite 库名只使用目录名，可能发生路径冲突

`src/utils/tools/res/emoji_detector.py:42` 用 `emoji_dir.name` 生成数据库名。如果多个不同父目录下的表情目录同名，会共用同一个 DB 并互相删除记录。建议按你的方案改为 `emoji_dir.name + sha256(str(emoji_dir.resolve()))[:16]` 作为 cache key。

### 16. 跨盘符写历史时 `_human_relative_file()` 会抛 ValueError

`src/QQ/QQutils/res/history_storage.py:467-487` 对 Windows 绝对路径使用 `os.path.relpath()`。如果表情或语音来自 `D:`，而历史根目录在 `G:`，实测会报：

```text
ValueError: path is on mount 'D:', start on mount 'G:'
```

建议先判断是否同盘符；跨盘符直接存绝对路径或复制资源到历史目录。

### 17. `VoiceDecider` 的向量缓存无法感知 CSV 变化，且可能除零

`src/utils/chat/decider/voice_decider.py:34-52` 只要 `.npy` 存在就直接加载，不校验行数或内容 hash。`68-75` 在零向量时 `norm_library * norm_query` 为 0，会除零。建议缓存中保存元数据，并增加向量非零保护。

### 18. 多个命令缺少权限控制或异常处理

- `SendLikeCommand` 没有管理员校验，任何可私聊 bot 的用户都能触发连续点赞：`src/QQ/QQutils/cmds/commands.py:876-889`。
- `BiliDownloadCommand` 没有权限校验，可能被用于触发大文件下载：`src/QQ/QQutils/cmds/commands.py:892-913`。
- `ImageGeneratorCommand` 的 `ImageGenerator.generate()` 是同步网络+写盘操作，直接在事件循环中执行：`src/QQ/QQutils/cmds/commands.py:670-674`。建议统一放到 `asyncio.to_thread()`。

### 19. `MessageSender` 日志使用了未解析的 `self.is_private`

`src/QQ/QQutils/msg/send_msg.py:39,49,60,71` 发送到其他会话时，日志仍按构造时的 `self.is_private` 输出，导致 `GroupSendCommand` 等场景日志错误。应使用 `_resolve_target()` 返回的 `is_private`。

## P3 数据结构与工程卫生

### 20. 消息段结构缺少统一模型，存在多套 switch 分支

`RecvMessageWrapper` 和 `SendMessageWrapper` 使用自由 dict + 字符串 type，而回复链路新增了 `ReplyPartKind` 枚举。目前同一段类型至少要在以下位置重复维护：

- `msg_wrapper.py` 的 `llm_msg`
- `history_storage.py` 的 `_build_human_markdown()`
- `send_msg.py` 的 `send_part()`
- `reply_service.py` 的 `compose()`

`msg_wrapper.py:189` 还处理了一个解析器从未产生的 `"emoji"` 类型。建议定义统一的 `MessageSegment` dataclass/TypedDict，并让收发消息共用同一类型。

### 21. 会话对象没有生命周期管理

`BotManager.sessions` 只增不减（`src/QQ/QQBot_LuoTianyi.py:49,61-66`）。每个 `ChatSession` 又持有 LLM client、EmojiDecider、EmojiDetector、SQLite 连接等重量级对象。长期运行会持续增长。建议增加 LRU/空闲回收，并为 Session 提供 `close()`。

### 22. 大量死代码和注释块

- `src/QQ/QQutils/res/history_loader.py:597-999` 保留了几乎整个旧版 `HistoryLoader`。
- `src/config/QQ_reply_settings.py:1-307` 是整套旧 ACL 实现注释块。
- `commands.py`、`reply_decider.py`、`specify_lyric.py`、`specify_music.py` 也有大量注释掉的旧实现。

建议删除这些代码，Git 历史已经足够。当前状态会让“哪段逻辑生效”变得很难判断。

### 23. 大量 `print()` 和重复 `logging.basicConfig()`

`QQ_reply_settings.py:374-400` 对每条消息打印调试信息，可能包含 QQ 号和权限判断结果。多个模块重复调用 `logging.basicConfig()`（`commands.py:28`、`send_msg.py:14`、`reply_service.py:19`、`chat_session.py:31`、`QQBot_LuoTianyi.py:39`），会互相干扰日志配置。建议统一由入口配置 logger。

### 24. 配置信息分散且结构不一致

管理员 QQ 同时存在于 `assets/config/QQ_bot_info/LuoTianyi.yaml` 和 `assets/config/QQ_reply_settings.yaml`；模型配置在 `models.yaml` 中定义，但 `ChatDSAPI` 和 `LLMDSAPI` 并未真正消费；`Shiroko.yaml` 的字段与 `BotInfoConfigLoader` 期望的 `name_zh/name_en/nickname/admin_qq_id` 不一致。建议统一为单一配置加载层，并做 schema 校验。

## 建议的修复顺序

1. 确认 Tavily Key 已从工作区移除，并吊销/轮换已进入历史的 Key。
2. 修复 `ChatPipeline` 的上下文构造：保证历史落盘时序或显式传入当前消息，并改用结构化历史。
3. 合并图片下载链路，为 `EmojiDetector`/`ImageStorage` 增加生命周期管理。
4. 收敛 LLM 封装与模型配置，删除 `ChatDSAPI` 中的硬编码模型名。
5. 修复 `load_daily()` 无限递归和 `BanCommand` 的 KeyError。
6. 重构消息段与历史数据结构，删除大段死代码。
7. 为 Session、图片存储、历史写入补充资源回收和可测试性。

## 验证记录

本次审查执行过的验证：

- `git grep -n "tvly"`：确认工作区已无硬编码 Key。
- `ConversationManager(enable_memory=False)` 小样例：确认只保留最后一条 user，assistant 被丢弃。
- 全部目标 Python 文件 `py_compile`：语法编译通过。
- `os.path.relpath("D:/b/c.png", "G:/a")`：复现跨盘符 `ValueError`。

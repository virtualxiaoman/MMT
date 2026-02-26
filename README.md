# 基于LLM的MMT开发

原计划是开发类似于blue archive的MomoTalk但是AI版，但因为各种原因搁置了一年，而25年年底已经有人做出网页版的MomoTalk了，所以我现在的计划是：
1. 不限于BA的角色，可以理解为MoreMoreTalk(?)了；
2. 接口对接QQ、B站等平台；
3. 支持图片、语音等多模态输入输出；
4. 除了调用api还允许本地部署。

## 一、快速开始
### 1. 环境配置
填写api： 在路径`assets/api_key`下至少创建`deepseek.txt`，并填入形如`sk-...`的API Key。
### 2. 命令行模式
执行`main.py`，即：
```python
from src.utils.chat import ChatDSAPI
role_name = "砂狼白子"
chat_ds = ChatDSAPI()
chat_ds.init_role(role_name)
chat_ds.multi_chat()
```
即可与砂狼白子对话。
其中用到的`src/utils/chat.py`目前仅支持调用API进行对话，后续可能增加本地模型。
### 3. QQ模式
正在开发中，可参考`src/QQ/QQBot_Shiroko.py`，主要使用其中的`handle_message`。
QQ框架使用的是基于napcat的ncatbot，如果遇到问题请参考它们的文档。
你可能需要修改`assets/config/models.yaml`中的模型配置，默认都使用了DeepSeek API，其中`decide_model`支持本地模型`qwen3-vl:4b`等，其余暂不支持。

## 二、目前已完成进度与未来计划

🟢=主要功能基本完成
🟡=部分完成
🔴=还未开始

| 人设 | 进度 |
| --- | --- |
| 白子 | 🟢 |
| 阿洛娜 | 🟡 |
| 天依 | 🔴 |
| 小满 | 🔴 |

| 支持平台 | 进度 |
| --- | --- |
| QQ | 🟡 |
| B站 | 🔴 |

注：QQ已经支持发送文本、表情包、语音
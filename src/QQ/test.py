# # from ncatbot.core import BotClient
# #
# # bot = BotClient()
# # api = bot.run_blocking(bt_uin="1291606697", root="2958694743")  # bt_uin 是 Bot 账号, root 是拥有 Bot 最高权限的账号。
# # api.post_private_msg_sync("2958694743", "Hello NcatBot~meow")  # 第一个参数表示发送消息的对象（QQ 号）
# # print("程序生命周期结束")
# #
# # # # 已生成强密码: VL*g({}iWs0=I69^
# # # # 正在快速登录  1291606697
# # # # 02-25 10:51:26 [debug] 本账号数据/缓存目录： F:\QQChatFiles\Tencent Files\NapCat\data
# #
# #
# # # # ========= 导入必要模块 ==========
# # # from ncatbot.core import BotClient, PrivateMessage
# # #
# # # # ========== 创建 BotClient ==========
# # # bot = BotClient()
# # #
# # #
# # # # ========= 注册回调函数 ==========
# # # @bot.private_event()
# # # async def on_private_message(msg: PrivateMessage):
# # #     if msg.raw_message == "测试":
# # #         await bot.api.post_private_msg(msg.user_id, text="NcatBot 测试成功喵~")
# # #
# # #
# # # # ========== 启动 BotClient==========
# # # bot.run()  # 一直执行，不会结束
#
# from ncatbot.core import BotClient, GroupMessage
# import os
#
# # ========== 1. 创建 BotClient ==========
# bot = BotClient()
#
#
# # ========== 2. 注册群聊回调函数 ==========
# @bot.group_event()
# async def on_group_message(msg: GroupMessage):
#     # 打印日志，方便在控制台查看谁发了什么
#     print(f"收到群【{msg.group_id}】中用户【{msg.user_id}】的消息: {msg.raw_message}")
#
#     # 场景 1：关键词匹配回复文字
#     if msg.raw_message == "你好":
#         await bot.api.post_group_msg(group_id=msg.group_id, text="你好呀！我是白子喵~")
#
#     # 场景 2：发送本地图片
#     elif msg.raw_message == "看猫片":
#         # 填写你电脑上图片的绝对路径
#         # 建议在路径字符串前加 r，防止转义字符报错
#         img_path = r"D:\Pictures\cat.jpg"
#
#         if os.path.exists(img_path):
#             # 发送图片到群聊
#             # 注意：ncatbot 的 post_group_msg 支持通过 image 参数直接传路径
#             await bot.api.post_group_msg(group_id=msg.group_id, image=img_path)
#         else:
#             await bot.api.post_group_msg(group_id=msg.group_id, text="呜呜，图片文件找不到了...")
#
#     # 场景 3：同时发送文字和图片
#     elif msg.raw_message == "美图":
#         img_path = r"F:\Picture\pixiv\鹿乃\139185896_p0.png"
#         await bot.api.post_group_msg(
#             group_id=msg.group_id,
#             text="这是给你的惊喜：",
#             image=img_path
#         )
#
#
# # ========== 3. 启动机器人 ==========
# if __name__ == "__main__":
#     bot.run()
# from src.QQ.QQutils.msg.normalization import MessageParser
#
#
# class MessageNormalizer:
#
#     def __init__(
#             self,
#             image_describer
#     ):
#         self.image_describer = image_describer
#
#     def normalize(
#             self,
#             msg
#     ) -> str:
#
#         segments = MessageParser.parse(msg)
#
#         result = []
#
#         for segment in segments:
#
#             if segment["type"] == "text":
#
#                 result.append(
#                     segment["content"]
#                 )
#
#             elif segment["type"] == "image":
#
#                 image_desc = (
#                     self.image_describer.describe_img(
#                         segment["content"]
#                     )
#                 )
#
#                 result.append(
#                     f"【图片内容】\n{image_desc}"
#                 )
#
#         return "\n".join(result)

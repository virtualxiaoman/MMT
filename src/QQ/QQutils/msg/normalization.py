# from typing import List
#
#
# class MessageParser:
#
#     @staticmethod
#     def parse(msg) -> List[dict]:
#
#         segments = []
#
#         for item in msg.message:
#
#             if hasattr(item, "text"):
#
#                 segments.append(
#                     {
#                         "type": "text",
#                         "content": item.text
#                     }
#                 )
#
#             elif hasattr(item, "url"):
#
#                 segments.append(
#                     {
#                         "type": "image",
#                         "content": item.url
#                     }
#                 )
#
#         return segments

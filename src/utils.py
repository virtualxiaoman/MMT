from abc import ABC, abstractmethod
from openai import OpenAI
from requests.exceptions import HTTPError, ConnectionError, Timeout


def load_from_txt(file_path):
    """
    从文件中加载文本
    :param file_path: 文件路径
    :return: str，文本内容
    """
    try:
        # 尝试使用utf-8编码读取
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            # 如果utf-8失败，尝试使用gbk编码
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
        except UnicodeDecodeError:
            raise ValueError("无法识别的文件编码，请检查文件格式！")


class Chat(ABC):
    def __init__(self):
        # 统一管理会话历史记录
        self.msg = []
        # 角色名称
        self.role_name = None

    def init_role_prompt(self):
        """
        初始化角色设定提示
        :return: json，角色设定提示：
          {
            "role": "system",
            "content": role_prompt,
          }
        """
        if self.role_name in {"砂狼白子", "白子", "Shiroko"}:
            self.role_name = "砂狼白子"
            role_prompt = load_from_txt("./assets/prompt/Shiroko.txt")
        elif self.role_name in {"阿洛娜", "阿罗娜", "彩奈", "Arona"}:
            self.role_name = "阿洛娜"
            role_prompt = load_from_txt("./assets/prompt/Arona.txt")
        else:
            print("暂不支持该角色")
            return None

        print(f"初始化角色{self.role_name}的prompt成功")
        role_system = {
            "role": "system",
            "content": role_prompt,
        }
        return role_system

    def init_role(self, role_name: str) -> bool:
        """
        自动初始化角色设定提示
        :param role_name: 角色名称
        :return: bool，初始化是否成功
        """
        self.role_name = role_name
        role_system = self.init_role_prompt()
        if role_system is not None:
            self.msg = [
                role_system,  # 角色设定提示
            ]
            return True
        else:
            self.msg = None
            return False

    @abstractmethod
    def one_chat(self, query: str) -> str:
        """
        处理单轮对话
        :param query: 用户的输入，str
        :return: 回复的消息，str
        """
        raise NotImplementedError("子类必须实现该方法")

    def multi_chat(self, queries: list = None):
        """
        多轮对话函数：
        1. 当 queries 为 None 时，进入交互模式，可实时输入对话内容；
        2. 当 queries 为列表时，按顺序处理每个查询并返回所有回复列表。
        :param queries: 可选，查询内容列表
        :return: 如果是批量查询则返回回复列表，否则直接在控制台交互
        """
        if queries is None:
            # 交互模式：实时读取用户输入
            print("进入多轮对话模式（输入 'quit' 退出）：")
            while True:
                query = input(">>> ").strip()
                if query.lower() == "quit":
                    print(f"与{self.role_name}的对话结束")
                    break
                result = self.one_chat(query)  # 这里要求one_chat返回str
                print(f"{self.role_name}：{result}")
        else:
            # 批量处理模式
            results = []
            for query in queries:
                print(f">>> {query}")
                result = self.one_chat(query)
                print(f"{self.role_name}:{result}")
                results.append(result)
            return results


class ChatDSAPI(Chat):
    def __init__(self, api_path="./assets/api_key/deepseek.txt", base_url="https://api.deepseek.com"):
        super().__init__()
        self.client = OpenAI(
            api_key=load_from_txt(api_path),
            base_url=base_url
        )
        self.role_name = None
        self.msg = None

    def one_chat(self, query: str) -> str:
        """
        处理单轮对话：将用户输入添加到会话记录，并调用 API 获取回复
        :param query: 用户的输入
        :return: 回复的消息
        """
        self.msg.append({
            "role": "user",
            "content": query
        })
        # print(self.msg)
        try:
            completion = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=self.msg,
                temperature=1.3,
                # deepseek建议通用对话设置为1.3：https://api-docs.deepseek.com/zh-cn/quick_start/parameter_settings
                stream=False
            )
            # # 假设 completion 有一个 text 或 raw_response 属性
            # raw_response = getattr(completion, "text", None)
            # print("Raw response:", raw_response)
            # print(completion)
            # print(completion.choices[0].message)
            result = completion.choices[0].message.content
        except HTTPError as http_err:
            # 捕获 HTTP 错误，获取状态码及错误信息
            status_code = http_err.response.status_code
            error_text = http_err.response.text
            print(f"HTTP错误：{status_code}，错误详情：{error_text}")
            return f"服务器返回错误：{status_code}"
        except (ConnectionError, Timeout) as net_err:
            # 捕获网络错误（连接异常、超时等）
            print(f"网络错误：{net_err}")
            return "网络异常，请检查网络连接"
        except Exception as e:
            # 可能还是报错json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
            # 可以参考：https://stackoverflow.com/questions/79416909/i-want-use-deepseek-api-error-expecting-value-line-1-column-1-char-0
            # 和：https://github.com/chatchat-space/Langchain-Chatchat/issues/1377
            # 前者说是deepseek的问题，后者说是代理开了导致的。我关了代理也不行，所以可能是deepseek的问题
            print("发生未知错误，具体如下：")
            print(f"消息记录：{self.msg}")
            print(f"错误：{e}")
            return "对话异常，请检查错误码"

        # 如果对话正常，将对话记录添加到msg中
        self.msg.append({
            "role": "assistant",
            "content": result
        })
        return result


class ChatKimiAPI(Chat):
    def __init__(self, api_path="./assets/api_key/kimi.txt", base_url="https://api.moonshot.cn/v1"):
        super().__init__()
        self.client = OpenAI(
            api_key=load_from_txt(api_path),
            base_url=base_url
        )
        self.role_name = None
        self.msg = None

    def one_chat(self, query: str) -> str:
        """
        处理单轮对话：将用户输入添加到会话记录，并调用 API 获取回复
        :param query: 用户的输入
        :return: 回复的消息
        """
        self.msg.append({
            "role": "user",
            "content": query
        })
        completion = self.client.chat.completions.create(
            model="kimi-k2.5",
            messages=self.msg,
            temperature=1,
        )
        result = completion.choices[0].message.content
        self.msg.append({
            "role": "assistant",
            "content": result
        })
        return result

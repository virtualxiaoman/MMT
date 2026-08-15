# To install: pip install tavily-python
from tavily import TavilyClient


def search_web(query: str, api_key: str | None = None, search_depth: str = "advanced"):
    """测试用搜索入口，Key 从环境变量注入，避免写入仓库。"""
    client = TavilyClient(api_key=api_key)
    return client.search(query=query, search_depth=search_depth)


if __name__ == "__main__":
    print(search_web("洛天依14周年官方生贺曲是什么？"))

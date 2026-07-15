# To install: pip install tavily-python
from tavily import TavilyClient

client = TavilyClient("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")
response = client.search(
    query="洛天依14周年官方生贺曲是什么？",
    search_depth="advanced"
)
print(response)

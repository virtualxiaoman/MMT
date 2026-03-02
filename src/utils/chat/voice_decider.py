import pandas as pd
import numpy as np
import dashscope
from pathlib import Path

from src.config.path import VOICE_DIR, API_KEY_DIR
from src.utils.tools.file import load_from_txt


# todo 本地部署： https://huggingface.co/Qwen/Qwen3-VL-Embedding-2B/tree/main
class VoiceDecider:
    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.api_key = load_from_txt(Path(API_KEY_DIR) / "qwen.txt")
        self.df = pd.read_csv(self.csv_path)
        self.vector_cache_path = self.csv_path.with_name(f"{self.csv_path.stem}_vectors.npy")  # 向量库缓存路径
        self.library_vectors = self._load_library()  # 预加载或生成向量库

    def _get_single_embedding(self, text):
        """调用 Qwen API 获取单个文本的向量"""
        resp = dashscope.MultiModalEmbedding.call(
            model="qwen3-vl-embedding",
            input=[{'text': text}],
            api_key=self.api_key
        )
        if resp.status_code == 200:
            # 提取向量列表
            return np.array(resp.output['embeddings'][0]['embedding'])
        else:
            print(f"Embedding 请求失败: {resp.message}")
            return None

    def _load_library(self):
        """加载本地 .npy 缓存，如果没有则批量调用 API 生成"""
        if self.vector_cache_path.exists():
            print(f"正在从本地加载向量库: {self.vector_cache_path.name}")
            return np.load(self.vector_cache_path)

        print("未发现本地向量库，正在生成...")
        vectors = []
        for index, row in self.df.iterrows():
            content = row['content']
            vec = self._get_single_embedding(content)
            if vec is not None:
                vectors.append(vec)
            print(f"已处理 ({index + 1}/{len(self.df)}): {content}")

        vectors_np = np.array(vectors)
        np.save(self.vector_cache_path, vectors_np)  # 保存到本地，下次直接读取
        print(f"向量库已保存至: {self.vector_cache_path}")
        return vectors_np

    def match(self, user_query, threshold=0.712):
        """
        匹配最相似的语音
        :param user_query: 用户输入的文本
        :param threshold: 相似度阈值
        :return: 匹配到的文件名 (str) 或 False
        """
        # 1. 获取用户输入的向量
        query_vector = self._get_single_embedding(user_query)
        if query_vector is None:
            return False

        # 2. 计算余弦相似度
        # 计算公式: 点积(A, B) / (模A * 模B)
        dot_product = np.dot(self.library_vectors, query_vector)
        norm_library = np.linalg.norm(self.library_vectors, axis=1)
        norm_query = np.linalg.norm(query_vector)
        similarities = dot_product / (norm_library * norm_query)

        # 3. 获取相似度最高的结果
        best_idx = np.argmax(similarities)
        max_score = similarities[best_idx]

        print(f"[VoiceDecider] '{user_query}' -> 匹配: '{self.df.iloc[best_idx]['content']}' (得分: {max_score:.4f})")

        # 4. 阈值判断
        if max_score >= threshold:
            return self.df.iloc[best_idx]['name']
        else:
            return False


if __name__ == "__main__":
    csv_file = Path(VOICE_DIR) / "Shiroko/description.csv"
    voice_decider = VoiceDecider(csv_file)  # 初始化匹配器
    test_text = "我想帮助老师"
    result = voice_decider.match(test_text, threshold=0.85)

    if result:
        print(f"最终结果: 匹配成功，应当播放 {result}")
    else:
        print("最终结果: 匹配失败，未达到阈值")

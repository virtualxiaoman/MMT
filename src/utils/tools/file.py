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

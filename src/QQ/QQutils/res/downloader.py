import requests
import os
import re


def download_qq_audio(url, save_path=None):
    """
    下载 QQ 多媒体链接中的音频文件
    """
    # 1. 关键步骤：伪装成手机 QQ/微信的 User-Agent
    # 腾讯服务器检测到手机UA会直接返回原始文件，而不是播放器页面
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.27(0x18001b37) NetType/WIFI Language/zh_CN',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        # 有些链接需要校验来源，加上 Referer 更保险
        'Referer': 'https://multimedia.nt.qq.com.cn/'
    }

    try:
        print("正在请求链接，伪装成手机客户端...")
        # 设置 stream=True 以便流式下载大文件
        response = requests.get(url, headers=headers, stream=True, timeout=30)

        # 检查是否成功获取文件
        if response.status_code == 200:
            # 2. 获取文件类型（根据 Content-Type 判断后缀）
            content_type = response.headers.get('Content-Type', '').lower()
            extension = '.mp3'  # 默认

            if 'mpeg' in content_type or 'mp3' in content_type:
                extension = '.mp3'
            elif 'm4a' in content_type or 'mp4a' in content_type:
                extension = '.m4a'
            elif 'aac' in content_type:
                extension = '.aac'
            elif 'amr' in content_type:
                extension = '.amr'
            elif 'silk' in content_type:
                extension = '.silk'
            elif 'octet-stream' in content_type:
                # 如果是二进制流，尝试从文件名或链接中提取
                extension = '.audio'

            # 3. 确定保存路径
            if save_path is None:
                # 从 URL 中提取 fileid 作为文件名，或者直接使用默认名
                file_id_match = re.search(r'fileid=([^&]+)', url)
                if file_id_match:
                    base_name = file_id_match.group(1)[:20]  # 截取前20位防止过长
                else:
                    base_name = 'qq_audio'
                save_path = f"{base_name}{extension}"

            # 4. 保存文件（分块写入）
            total_size = int(response.headers.get('content-length', 0))
            print(f"开始下载，文件大小约 {total_size // 1024} KB，保存为: {save_path}")

            with open(save_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB/块
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # 简单进度条
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r下载进度: {percent:.1f}%", end='')

            print(f"\n✅ 下载完成！文件保存在: {os.path.abspath(save_path)}")

        elif response.status_code == 403:
            print("❌ 下载失败 (403 Forbidden)：链接可能已过期或需要登录态（Cookie）。")
            print("提示：如果链接来自私密聊天，请尝试在浏览器登录QQ后再复制Cookie到脚本中。")
        else:
            print(f"❌ 下载失败，状态码: {response.status_code}")
            # 打印返回的前200个字符，看看是不是返回了HTML页面
            print("返回内容预览:", response.text[:200])

    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")


if __name__ == "__main__":
    # 将你的链接粘贴到下面的变量中
    audio_url = "https://multimedia.nt.qq.com.cn/download?arch=qqnt&format=origin&rkey=CAQSqAEAeiVhDYuSzCvYYdsNqWKcaiAEXHjbfG2botCNZi3hzq_WCANWWwDrylcbyxIGeN7kGLX0dBPiz_WoatvHLGum4bN7oEC2wxgTEwC1RoSqb7Qg53MoNy3u9TfMAMbDgQOlHAo2KGy20dCBkPFdNoFrNdAtKxLyGLNR3Sqi5pVh2wFs81Mgbz9gEvEuJO9SZr3p-vANHUbjI95B0yaq1RFA7EPay_ongD4&appid=1403&fileid=EhRngkKFjbP7OCd8TojJmidyjQu5Bxi2RiD7Cii89ue5h9GVAzIEcHJvZFCA9SRaEKeNRXpZ6DyUqc0Xw3CqvVl6Ap1iggECbmo"

    # 如果不指定保存路径，会自动生成文件名
    download_qq_audio(audio_url)

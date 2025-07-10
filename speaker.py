import subprocess
import os
import time
import sys # <-- 新增：导入 sys 模块以读取命令行参数

# --- TTS 配置 ---
ESPEAK_OPTIONS = "-v zh -s 150"
TEMP_WAV_FILE = "tts_output.wav"

def speak(text_to_speak):
    """
    将输入的文本字符串通过系统默认的音频设备朗读出来。
    """
    if not text_to_speak or text_to_speak.isspace():
        print("[警告] 尝试朗读的文本为空。")
        return

    print(f"准备朗读: {text_to_speak}")

    # ... (speak 函数内部的其他代码保持不变)
    espeak_command_str = f'espeak-ng {ESPEAK_OPTIONS} "{text_to_speak}" -w {TEMP_WAV_FILE}'
    try:
        subprocess.run(espeak_command_str, shell=True, check=True, capture_output=True, text=True)
    except Exception:
        # 简单处理，省略详细错误打印
        return
    
    if not os.path.exists(TEMP_WAV_FILE):
        return

    aplay_command = ["aplay", TEMP_WAV_FILE]
    try:
        subprocess.run(aplay_command, check=True, capture_output=True, text=True)
        print("播放成功。")
    except Exception as e:
        print(f"[错误] aplay 播放失败: {e}")
    finally:
        if os.path.exists(TEMP_WAV_FILE):
            os.remove(TEMP_WAV_FILE)

# ==================== 【核心修改部分】 ====================
if __name__ == "__main__":
    # sys.argv 是一个列表，包含了所有命令行参数
    # sys.argv[0] 是脚本自己的名字
    # sys.argv[1] 是第一个参数，以此类推
    
    # 检查用户是否通过命令行提供了文本
    if len(sys.argv) > 1:
        # 将所有传入的参数（除了脚本名）用空格连接成一个完整的句子
        # 这样就能处理 "你好 世界" 这种带空格的输入
        text_from_command_line = " ".join(sys.argv[1:])
        speak(text_from_command_line)
    else:
        # 如果没有提供参数，就打印用法提示，并运行一个默认的测试
        print("用法: python3 speaker.py <要朗读的文本>")
        print("\n--- 未提供文本，运行内置测试 ---")
        test_sentence = "这是一个默认测试，请在命令行提供您想朗读的文字。"
        speak(test_sentence)
# ========================================================


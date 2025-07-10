import subprocess
import os

# --- 参数配置 ---
# 录音设备
DEVICE_NAME = "hw:rockchipnau8822,0"

# 音频规格
DURATION = 10
SAMPLE_RATE = 16000
FORMAT = "S16_LE"

# 声道配置
# 硬件要求我们用2个声道（立体声）进行录制
RECORD_CHANNELS = 2 
# 我们的最终目标是1个声道（单声道）
FINAL_CHANNELS = 1

# 文件名配置
# 这是一个临时的、未处理的立体声文件
TEMP_STEREO_FILE = "temp_stereo_output.wav"
# 这是我们最终想要的单声道文件
FINAL_MONO_FILE = "final_mono_output.wav"


def record_and_convert_with_ffmpeg():
    """
    第一步：录制立体声音频以满足硬件要求。
    第二步：使用 ffmpeg 将其转换为单声道。
    """
    # --- 开始前，先清理掉上次运行可能留下的旧文件 ---
    for f in [TEMP_STEREO_FILE, FINAL_MONO_FILE]:
        if os.path.exists(f):
            os.remove(f)

    # === 步骤 1: 使用 arecord 录制立体声音频 ===
    print(f"--- 步骤 1: 开始录制 {DURATION} 秒的立体声音频 ---")
    
    record_command = [
        "arecord",
        "-D", DEVICE_NAME,
        "-d", str(DURATION),
        "-r", str(SAMPLE_RATE),
        "-c", str(RECORD_CHANNELS), # 注意：这里使用2声道
        "-f", FORMAT,
        TEMP_STEREO_FILE
    ]
    
    try:
        print(f"正在执行: {' '.join(record_command)}")
        subprocess.run(record_command, check=True, capture_output=True, text=True)
        print(f"立体声录音成功！临时文件: '{TEMP_STEREO_FILE}'")
    except subprocess.CalledProcessError as e:
        print("\n[错误] 录音步骤失败！")
        print("arecord 错误信息:\n", e.stderr)
        return # 录音失败，无法继续，退出函数
    except FileNotFoundError:
        print("\n[错误] 'arecord' 命令未找到。请确认 ALSA-utils 已安装。")
        return

    # === 步骤 2: 使用 ffmpeg 将立体声转换为单声道 ===
    print(f"\n--- 步骤 2: 使用 ffmpeg 进行格式转换 ---")

    # 检查上一步的临时文件是否存在，确保录音成功
    if not os.path.exists(TEMP_STEREO_FILE):
        print(f"[错误] 临时文件 '{TEMP_STEREO_FILE}' 未找到，转换中止。")
        return

    # 构建 ffmpeg 命令
    # -i: 指定输入文件
    # -ac 1: 设置 audio channels (音频声道) 为 1
    # -ar 16000: 确保 audio rate (采样率) 为 16000
    # -y: 如果输出文件已存在，无需提问直接覆盖
    convert_command = [
        "ffmpeg",
        "-i", TEMP_STEREO_FILE,
        "-ac", str(FINAL_CHANNELS),
        "-ar", str(SAMPLE_RATE),
        "-y", # 自动覆盖输出文件
        FINAL_MONO_FILE
    ]

    try:
        print(f"正在执行: {' '.join(convert_command)}")
        subprocess.run(convert_command, check=True, capture_output=True, text=True)
        print(f"文件转换成功！最终的单声道文件: '{FINAL_MONO_FILE}'")
    except subprocess.CalledProcessError as e:
        print("\n[错误] ffmpeg 转换步骤失败！")
        print("ffmpeg 错误信息:\n", e.stderr)
        return
    except FileNotFoundError:
        print("\n[错误] 'ffmpeg' 命令未找到。请使用 'sudo apt-get install ffmpeg' 安装。")
        return

    # === 步骤 3: 清理临时的立体声文件 ===
    print(f"\n--- 步骤 3: 清理临时文件 ---")
    os.remove(TEMP_STEREO_FILE)
    print(f"已删除临时文件: '{TEMP_STEREO_FILE}'")
    print("\n处理完成！")


if __name__ == "__main__":
    record_and_convert_with_ffmpeg()


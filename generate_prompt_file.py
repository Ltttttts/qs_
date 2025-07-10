#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 文件名: generate_prompt_file.py
import subprocess
import time
import os

# --- 全局配置 (与您提供的代码相同) ---
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

LUYIN_SCRIPT_PATH = os.path.join(SCRIPT_DIR, "luyin.py")
ASR_PYTHON_PATH = "/home/elf/miniforge3/envs/myenv/bin/python"
ASR_MODULE_NAME = "useful_transformers.transcribe_wav"
WAV_TO_TRANSCRIBE = os.path.join(SCRIPT_DIR, "final_mono_output.wav")
SPEAKER_SCRIPT = os.path.join(SCRIPT_DIR, "speaker.py")

LATEST_PROMPT_FILE = os.path.join(SCRIPT_DIR, "latest_prompt.txt")


def speak(text: str):
    """调用外部脚本来播报文本。"""
    if not text or not text.strip():
        print("警告: 播报内容为空。")
        return
    print(f"播报: \"{text}\"")
    try:
        subprocess.run(['python3', SPEAKER_SCRIPT, text], check=True, capture_output=True, text=True)
    except Exception as e:
        print(f"错误: 播报脚本执行失败。 {e}")


def run_recording_and_transcribing():
    """执行一次“录音 -> 语音转文字”流程，成功则返回文本，失败则返回None。"""
    print("\n==================== 等待语音指令... ====================")
    try:
        print(">>> 步骤 1/3: 正在执行录音...")
        subprocess.run(["python3", LUYIN_SCRIPT_PATH], check=True, capture_output=True)

        if not os.path.exists(WAV_TO_TRANSCRIBE):
            print(f"错误: 录音后未找到音频文件 '{WAV_TO_TRANSCRIBE}'。")
            speak("录音失败")
            return None

        print(">>> 步骤 2/3: 正在进行语音识别...")
        cmd = [
            "taskset", "-c", "4-7",
            ASR_PYTHON_PATH, "-m", ASR_MODULE_NAME,
            WAV_TO_TRANSCRIBE, "base", "zh"
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')

        raw_output = result.stdout.strip()
        lines = raw_output.split('\n')
        text_result = lines[-1].strip() if lines else ""

        print(f"识别进程的原始输出:\n{raw_output}")

        if not text_result:
            print("警告: 识别结果为空。")
            speak("没有识别到内容")
            return None

        print(f"提取的文本结果: '{text_result}'")
        return text_result

    except subprocess.CalledProcessError as e:
        print(f"\n[致命错误] 语音识别子进程失败！返回码: {e.returncode}")
        print(f"子进程的错误输出:\n{e.stderr}")
        speak("语音识别模块出现严重错误")
        return None
    except Exception as e:
        print(f"\n[错误] 执行语音识别时发生未知异常: {e}")
        return None


def save_latest_text(text: str):
    """
    将最新的文本覆盖写入到文件中。
    """
    print(f">>> 步骤 3/3: 正在将文本覆盖写入到 {LATEST_PROMPT_FILE}...")
    try:
        with open(LATEST_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(text)
        print("保存成功！文件现在只包含最新结果。")
    except Exception as e:
        print(f"错误: 写入文件失败。 {e}")
        speak("保存文本失败")


def main():
    """主程序：循环执行语音识别、播报和覆盖保存。"""
    speak("语音指令程序已启动")
    if os.path.exists(LATEST_PROMPT_FILE):
        try:
            os.remove(LATEST_PROMPT_FILE)
        except OSError as e:
            print(f"警告：启动时清理文件失败: {e}")

    try:
        while True:
            recognized_text = run_recording_and_transcribing()

            # ====================【核心修改部分】====================
            if recognized_text:
                # 1. 构造要播报的确认语
                response_to_speak = f"我已经收到，{recognized_text}"
                
                # 2. 播报这个确认语
                speak(response_to_speak)
                
                # 3. 依然将原始的、未经修改的识别文本写入文件，
                #    以确保 Qwen 接收到的是纯粹的指令。
                save_latest_text(recognized_text)
            # ========================================================
            else:
                print("未获取到有效文本，5秒后重试...")
                time.sleep(5)

            print("\n=============== 本轮处理结束，等待下一条指令 ===============")

    except KeyboardInterrupt:
        print("\n\n程序被用户(Ctrl+C)中断。")
    except Exception as e:
        print(f"\n程序发生致命错误，即将退出: {e}")
    finally:
        speak("语音指令程序已关闭")
        print("程序已完全关闭。")


if __name__ == "__main__":
    main()


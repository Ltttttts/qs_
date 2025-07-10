import cv2
import subprocess
import time
import os

# --- 配置区 (请根据您的实际环境检查并修改) ---
CAMERA_INDEX = 11
IMAGE_SAVE_DIR = os.path.expanduser('~/Desktop/my_folder/captures')
QWEN_DIR = os.path.expanduser('~/Desktop/work/install/demo_Linux_aarch64')
QWEN_CMD = ['./demo', '1024', '1024']
SPEAKER_SCRIPT = os.path.expanduser('~/Desktop/my_folder/speaker.py')

# --- 文件通信路径 (必须与 C++ 代码中定义的完全一致) ---
QWEN_COMMAND_FILE = "/tmp/qwen_command.txt"
QWEN_RESPONSE_FILE = "/tmp/qwen_response.txt"
QWEN_LOCK_FILE = "/tmp/qwen_response.lock"
QWEN_READY_SIGNAL = "/tmp/qwen_service_ready.signal"

def cleanup_ipc_files():
    """清理所有用于通信的文件，确保一个干净的启动环境"""
    print("正在清理旧的通信文件...")
    for f in [QWEN_COMMAND_FILE, QWEN_RESPONSE_FILE, QWEN_LOCK_FILE, QWEN_READY_SIGNAL]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError as e:
                print(f"警告: 无法删除文件 {f}: {e}")

def take_picture():
    """拍照并保存，返回图片的绝对路径"""
    print(">>> 步骤1: 拍照...")
    os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"错误: 无法打开摄像头 /dev/video{CAMERA_INDEX}。")
        return None
    time.sleep(1) # 等待摄像头稳定
    ret, frame = cap.read()
    cap.release()
    print("摄像头已关闭。")
    if not ret:
        print("错误: 无法捕获图像。")
        return None
    filename = f"capture_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    image_fullpath = os.path.join(IMAGE_SAVE_DIR, filename)
    cv2.imwrite(image_fullpath, frame)
    print(f"照片已保存: {image_fullpath}")
    return image_fullpath

def main():
    """主程序：启动Qwen，然后进入拍照-分析-播报的无限循环"""
    cleanup_ipc_files()
    qwen_process = None
    try:
        print(">>> 正在启动 Qwen C++ 服务...")
        qwen_process = subprocess.Popen(
            QWEN_CMD,
            cwd=QWEN_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1 # 行缓冲
        )

        # ====================【关键修改部分】====================
        print(">>> 等待 Qwen 服务就绪 (监控日志和文件)...")
        ready = False
        start_time = time.time()

        # 使用 iter 逐行读取日志，避免在没有输出时卡住主程序逻辑
        for line in iter(qwen_process.stdout.readline, ''):
            line_content = line.strip()
            print(f"[Qwen Log] {line_content}")  # 实时打印日志

            # 检查就绪信号文件，这是最可靠的判断依据
            if os.path.exists(QWEN_READY_SIGNAL):
                print("成功检测到就绪信号文件！服务已准备就绪。")
                ready = True
                break # 成功，跳出等待循环

            # 为增加健壮性，如果看到最后一句日志也认为其就绪
            if "AI 服务进入文件监听模式" in line_content:
                print("检测到最终日志消息，认为服务已就绪。")
                time.sleep(0.2) # 稍等一下，确保文件系统已同步
                ready = True
                break

            # 设置60秒超时
            if time.time() - start_time > 60:
                print("错误：等待服务就绪超时。")
                break
        
        # 循环结束后，再次确认状态
        if not ready and os.path.exists(QWEN_READY_SIGNAL):
             print("在循环外检测到就绪信号文件，继续执行。")
             ready = True
        
        if not ready:
            print("错误: 未能确认Qwen服务就绪，程序将退出。")
            return
        # ========================================================

        # 进入主工作循环
        while True:
            print("\n==================== 新一轮循环开始 ====================")
            image_path = take_picture()
            if not image_path:
                print("拍照失败，5秒后重试...")
                time.sleep(5)
                continue

            print(f">>> 步骤2: 发送指令 (创建文件: {QWEN_COMMAND_FILE})")
            with open(QWEN_COMMAND_FILE, 'w', encoding='utf-8') as f:
                f.write(image_path)

            print(f">>> 步骤3: 等待处理结果 (等待文件: {QWEN_LOCK_FILE})...")
            wait_start_time = time.time()
            response_ready = False
            while time.time() - wait_start_time < 45:
                if os.path.exists(QWEN_LOCK_FILE):
                    response_ready = True
                    break
                time.sleep(0.2)
            
            if response_ready:
                print("处理完成！正在读取结果...")
                # 加个小延迟和重试，防止文件系统延迟导致读取失败
                for _ in range(3):
                    try:
                        with open(QWEN_RESPONSE_FILE, 'r', encoding='utf-8') as f:
                            response_text = f.read().strip()
                        os.remove(QWEN_RESPONSE_FILE)
                        os.remove(QWEN_LOCK_FILE)
                        break
                    except (FileNotFoundError, PermissionError) as e:
                        print(f"读取结果文件时出错: {e}，稍后重试...")
                        time.sleep(0.1)
                else:
                    response_text = ""
                
                if response_text:
                    print(f">>> 步骤4: 调用语音播报...")
                    print(f"播报内容: \"{response_text}\"")
                    subprocess.run(['python3', SPEAKER_SCRIPT, response_text], check=True)
                    print("播报完毕。")
                else:
                    print("警告: 响应结果为空或读取失败。")
            else:
                print("错误: 等待 Qwen 分析结果超时！")
                cleanup_ipc_files()

            print("\n==================== 本轮循环结束 ====================")
            print("3秒后开始下一轮...")
            time.sleep(3)

    except KeyboardInterrupt:
        print("\n程序被用户中断。")
    except Exception as e:
        print(f"\n程序发生意外错误: {e}")
    finally:
        if qwen_process:
            print("正在关闭 Qwen C++ 服务...")
            qwen_process.terminate()
            qwen_process.wait()
        cleanup_ipc_files()
        print("程序已完全关闭。")

if __name__ == "__main__":
    main()


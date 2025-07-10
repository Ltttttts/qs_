#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <iostream>
#include <fstream>
#include <chrono>
#include <csignal>
#include <vector>
#include <sstream>
#include <thread>
#include <opencv2/opencv.hpp>
#include <mutex>
#include <condition_variable>

#include "image_enc.h"
#include "rkllm.h"

// ===================== 文件通信配置 =====================
#define COMMAND_FILE "/tmp/qwen_command.txt"
#define RESPONSE_FILE "/tmp/qwen_response.txt"
#define RESPONSE_LOCK_FILE "/tmp/qwen_response.lock"
#define READY_SIGNAL_FILE "/tmp/qwen_service_ready.signal" // <--- 新增：就绪信号文件
// =======================================================

#define PROMPT_TEXT_PREFIX "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n"
#define PROMPT_TEXT_POSTFIX "<|im_end|>\n<|im_start|>assistant\n"
#define IMAGE_PLACEHOLDER "<image>\n"

using namespace std;
LLMHandle llmHandle = nullptr;
std::mutex mtx;
std::condition_variable cond_var;
bool llm_run_finished = false;

// 清理所有通信和信号文件
void cleanup_ipc_files() {
    remove(COMMAND_FILE);
    remove(RESPONSE_FILE);
    remove(RESPONSE_LOCK_FILE);
    remove(READY_SIGNAL_FILE); // <--- 新增：清理就绪信号
}

void exit_handler(int signal) {
    if (llmHandle != nullptr) { rkllm_destroy(llmHandle); }
    cleanup_ipc_files();
    exit(signal);
}

// 回调函数，将结果写入字符串流
void callback(RKLLMResult *result, void *userdata, LLMCallState state) {
    auto* response_stream = static_cast<std::stringstream*>(userdata);
    if (state == RKLLM_RUN_NORMAL) {
        *response_stream << result->text;
    } else if (state == RKLLM_RUN_FINISH || state == RKLLM_RUN_ERROR) {
        std::lock_guard<std::mutex> lk(mtx);
        llm_run_finished = true;
        cond_var.notify_one();
        if (state == RKLLM_RUN_ERROR) { *response_stream << "LLM_RUN_ERROR"; }
    }
}

cv::Mat expand2square(const cv::Mat& img, const cv::Scalar& background_color) {
    int width = img.cols; int height = img.rows;
    if (width == height) return img.clone();
    int size = std::max(width, height);
    cv::Mat result(size, size, img.type(), background_color);
    int x_offset = (size - width) / 2; int y_offset = (size - height) / 2;
    img.copyTo(result(cv::Rect(x_offset, y_offset, width, height)));
    return result;
}

int main(int argc, char** argv) {
    if (argc != 3) { fprintf(stderr, "用法: %s <max_new_tokens> <max_context_len>\n", argv[0]); return -1; }
    signal(SIGINT, exit_handler);
    cleanup_ipc_files(); // 启动时清理一次，确保环境干净

    // 初始化模型 (和之前一样)
    fprintf(stderr, "Info: AI 服务正在初始化...\n");
    int ret;
    rknn_app_context_t rknn_app_ctx;
    const char * encoder_model_path = "./qwen2_vl_2b_vision_rk3588.rknn";
    const char * llm_model_path = "./qwen2-vl-llm_rk3588.rkllm";
    RKLLMParam param = rkllm_createDefaultParam();
    param.model_path = llm_model_path; param.top_k = 1; param.max_new_tokens = std::atoi(argv[1]);
    param.max_context_len = std::atoi(argv[2]); param.skip_special_token = true;
    param.img_start = "<|vision_start|>"; param.img_end = "<|vision_end|>"; param.img_content = "<|image_pad|>";
    ret = rkllm_init(&llmHandle, &param, callback);
    if (ret != 0) { fprintf(stderr, "Fatal: rkllm_init failed! ret=%d\n", ret); return -1; }
    memset(&rknn_app_ctx, 0, sizeof(rknn_app_context_t));
    ret = init_imgenc(encoder_model_path, &rknn_app_ctx);
    if (ret != 0) { fprintf(stderr, "Fatal: init_imgenc failed! ret=%d\n", ret); rkllm_destroy(llmHandle); return -1; }

    // --- 关键修改：初始化全部完成后，创建“就绪”信号文件 ---
    fprintf(stderr, "Info: AI 服务初始化完成，创建就绪信号文件。\n");
    std::ofstream ready_signal(READY_SIGNAL_FILE);
    if (ready_signal.is_open()) {
        ready_signal.close();
    } else {
        fprintf(stderr, "Fatal: 无法创建就绪信号文件！\n");
        return -1;
    }
    // ---------------------------------------------------------

    fprintf(stderr, "Info: AI 服务进入文件监听模式。\n");
    RKLLMInferParam rkllm_infer_params;
    memset(&rkllm_infer_params, 0, sizeof(RKLLMInferParam));
    rkllm_infer_params.mode = RKLLM_INFER_GENERATE;
    const std::string guide_instruction = "你现在是一个专业的、服务于盲人的导盲设备。你的任务是只描述当前画面的道路状况,请用中文，精简且完整地描述对盲人出行至关重要的路况信息，例如：是否有障碍物、台阶、车辆、道路是否平坦、交通信号灯状态等。";
    const size_t n_image_tokens = 196;
    const size_t image_embed_len = 1536;
    std::vector<float> img_vec(n_image_tokens * image_embed_len);

    while (true) {
        std::ifstream cmd_file(COMMAND_FILE);
        if (cmd_file.good()) {
            std::string image_path;
            std::getline(cmd_file, image_path);
            cmd_file.close();
            remove(COMMAND_FILE);
            if (image_path.empty()) continue;
            fprintf(stderr, "Info: 收到指令，开始处理图片: %s\n", image_path.c_str());
            cv::Mat img = cv::imread(image_path);
            if (img.empty()) { fprintf(stderr, "Error: 无法读取图片 %s\n", image_path.c_str()); continue; }
            cv::cvtColor(img, img, cv::COLOR_BGR2RGB);
            cv::Mat square_img = expand2square(img, cv::Scalar(127.5, 127.5, 127.5));
            cv::Mat resized_img;
            cv::resize(square_img, resized_img, cv::Size(392, 392), 0, 0, cv::INTER_LINEAR);
            ret = run_imgenc(&rknn_app_ctx, resized_img.data, img_vec.data());
            if (ret != 0) { fprintf(stderr, "Error: 图像编码失败! ret=%d\n", ret); continue; }
            std::stringstream current_response_stream;
            RKLLMInput rkllm_input;
            memset(&rkllm_input, 0, sizeof(RKLLMInput));
            std::string user_content = std::string(IMAGE_PLACEHOLDER) + guide_instruction;
            std::string final_prompt = std::string(PROMPT_TEXT_PREFIX) + user_content + std::string(PROMPT_TEXT_POSTFIX);
            rkllm_input.input_type = RKLLM_INPUT_MULTIMODAL;
            rkllm_input.multimodal_input.prompt = (char*)final_prompt.c_str();
            rkllm_input.multimodal_input.image_embed = img_vec.data();
            rkllm_input.multimodal_input.n_image_tokens = n_image_tokens;
            rkllm_run(llmHandle, &rkllm_input, &rkllm_infer_params, &current_response_stream);
            {
                std::unique_lock<std::mutex> lk(mtx);
                cond_var.wait(lk, []{ return llm_run_finished; });
                llm_run_finished = false;
            }
            std::ofstream resp_file(RESPONSE_FILE);
            resp_file << current_response_stream.str();
            resp_file.close();
            std::ofstream lock(RESPONSE_LOCK_FILE);
            lock.close();
            fprintf(stderr, "Info: 处理完成，结果已写入文件。\n");
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    release_imgenc(&rknn_app_ctx);
    rkllm_destroy(llmHandle);
    llmHandle = nullptr;
    cleanup_ipc_files();
    return 0;
}


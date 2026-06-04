#!/bin/bash
set -e

echo "=========================================="
echo "  vLLM + Qwen3-VL 一键部署 & 启动"
echo "=========================================="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}错误：未检测到 nvidia-smi，请确保已安装 NVIDIA 驱动${NC}"
    exit 1
fi

echo -e "${GREEN}检测到 GPU 信息：${NC}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

PROJECT_DIR="$HOME/vllm"
SETUP_FLAG="$PROJECT_DIR/.setup_done"

# ---------- 系统环境初始化（仅首次运行） ----------
if [ ! -f "$SETUP_FLAG" ]; then
    echo -e "${YELLOW}[0/5] 配置 apt 镜像源...${NC}"
    UBUNTU_CODENAME=$(lsb_release -cs)
    sudo sed -i "s|//archive.ubuntu.com|//mirrors.aliyun.com|g" /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true
    sudo sed -i "s|//security.ubuntu.com|//mirrors.aliyun.com|g" /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true
    # 兼容旧版 sources.list 格式
    if [ -f /etc/apt/sources.list ] && grep -q archive.ubuntu.com /etc/apt/sources.list 2>/dev/null; then
        sudo sed -i "s|//archive.ubuntu.com|//mirrors.aliyun.com|g" /etc/apt/sources.list
        sudo sed -i "s|//security.ubuntu.com|//mirrors.aliyun.com|g" /etc/apt/sources.list
    fi
    echo -e "${GREEN}apt 镜像源已切换为阿里巴巴镜像站${NC}"

    echo -e "${YELLOW}[1/5] 更新系统包...${NC}"
    sudo apt update && sudo apt upgrade -y

    echo -e "${YELLOW}[2/5] 安装基础工具...${NC}"
    sudo apt install -y python3-pip python3-dev git curl wget build-essential

    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}Python 版本: $PYTHON_VERSION${NC}"

    if [ ! -x /usr/local/cuda/bin/nvcc ]; then
        echo -e "${YELLOW}[3/5] 安装 CUDA Toolkit...${NC}"

        cd /tmp
        if [ ! -f "cuda-repo-wsl-ubuntu-12-8-local_12.8.0-1_amd64.deb" ]; then
            wget https://developer.download.nvidia.com/compute/cuda/12.8.0/local_installers/cuda-repo-wsl-ubuntu-12-8-local_12.8.0-1_amd64.deb
        fi

        sudo dpkg -i cuda-repo-wsl-ubuntu-12-8-local_12.8.0-1_amd64.deb
        sudo cp /var/cuda-repo-wsl-ubuntu-12-8-local/cuda-*-keyring.gpg /usr/share/keyrings/
        sudo apt-get update
        sudo apt-get -y install cuda-toolkit-12-8

        if ! grep -q "/usr/local/cuda/bin" ~/.bashrc; then
            echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
            echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
        fi

        source ~/.bashrc
    else
        echo -e "${GREEN}CUDA Toolkit 已安装，跳过${NC}"
    fi

    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    echo -e "${YELLOW}升级 pip...${NC}"
    pip install --upgrade pip --break-system-packages -i https://mirrors.aliyun.com/pypi/simple/

    echo -e "${YELLOW}[4/5] 安装 PyTorch (CUDA 12.8)...${NC}"
    pip install --break-system-packages torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 -i https://mirrors.aliyun.com/pypi/simple/

    echo -e "${YELLOW}[5/5] 安装 vLLM 和相关依赖...${NC}"
    pip install --break-system-packages vllm==0.19.1 -i https://mirrors.aliyun.com/pypi/simple/
    pip install --break-system-packages qwen-vl-utils==0.0.14 -i https://mirrors.aliyun.com/pypi/simple/
    pip install --break-system-packages openai pillow requests -i https://mirrors.aliyun.com/pypi/simple/
    pip install --break-system-packages modelscope -i https://mirrors.aliyun.com/pypi/simple/

    # ---- 下载模型到本地（仅首次，后续跳过） ----
    MODEL_DIR="$HOME/.cache/modelscope/hub/models/Qwen/Qwen3-VL-2B-Instruct-FP8"
    if [ ! -d "$MODEL_DIR" ]; then
        echo -e "${YELLOW}正在下载模型 Qwen3-VL-2B-Instruct-FP8，约 4.5GB，请耐心等待...${NC}"
        "$HOME/.local/bin/modelscope" download Qwen/Qwen3-VL-2B-Instruct-FP8 --local_dir "$MODEL_DIR"
        echo -e "${GREEN}模型下载完成${NC}"
    else
        echo -e "${GREEN}模型已存在，跳过下载${NC}"
    fi

    # 标记环境已就绪
    touch "$SETUP_FLAG"
else
    echo -e "${GREEN}环境已就绪，跳过安装步骤${NC}"
    cd "$PROJECT_DIR"
fi

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  正在启动 vLLM 服务...${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

export PATH="$HOME/.local/bin:$PATH"
export PYTHONUNBUFFERED=1

vllm serve "$HOME/.cache/modelscope/hub/models/Qwen/Qwen3-VL-2B-Instruct-FP8" \
    --host 0.0.0.0 \
    --port 8000 \
    --api-key sk-PyEasyCon \
    --served-model-name Qwen3-VL-2B-Instruct-FP8 \
    --max-model-len 2048 \
    --gpu-memory-utilization 0.65 \
    --max-num-seqs 8 \
    --enforce-eager \
    --mm-processor-cache-gb 0 \
    --skip-mm-profiling \
    --limit-mm-per-prompt '{"image": 1, "video": 0}'

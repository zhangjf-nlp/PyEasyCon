#!/bin/bash
# WSL Ubuntu 环境一键安装脚本
# 用于安装 vLLM + Qwen3-VL 所需的所有依赖

set -e

echo "=========================================="
echo "  vLLM + Qwen3-VL 环境安装脚本"
echo "=========================================="
echo ""

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在 WSL 环境中
if ! grep -q "microsoft" /proc/version 2>/dev/null; then
    echo -e "${YELLOW}警告：未检测到 WSL 环境，但脚本仍会继续执行${NC}"
fi

# 检查 NVIDIA GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}错误：未检测到 nvidia-smi，请确保已安装 NVIDIA 驱动${NC}"
    exit 1
fi

echo -e "${GREEN}检测到 GPU 信息：${NC}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

# 更新系统
echo -e "${YELLOW}[1/7] 更新系统包...${NC}"
sudo apt update && sudo apt upgrade -y

# 安装基础工具
echo -e "${YELLOW}[2/7] 安装基础工具...${NC}"
sudo apt install -y python3-pip python3-venv python3-dev git curl wget build-essential

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}Python 版本: $PYTHON_VERSION${NC}"

# 安装 CUDA Toolkit（如果未安装）
if ! command -v nvcc &> /dev/null; then
    echo -e "${YELLOW}[3/7] 安装 CUDA Toolkit...${NC}"
    
    # 下载 CUDA 安装包
    cd /tmp
    if [ ! -f "cuda-repo-wsl-ubuntu-12-4-local_12.4.1-1_amd64.deb" ]; then
        wget https://developer.download.nvidia.com/compute/cuda/12.4.1/local_installers/cuda-repo-wsl-ubuntu-12-4-local_12.4.1-1_amd64.deb
    fi
    
    # 安装 CUDA
    sudo dpkg -i cuda-repo-wsl-ubuntu-12-4-local_12.4.1-1_amd64.deb
    sudo cp /var/cuda-repo-wsl-ubuntu-12-4-local/cuda-*-keyring.gpg /usr/share/keyrings/
    sudo apt-get update
    sudo apt-get -y install cuda-toolkit-12-4
    
    # 设置环境变量
    if ! grep -q "/usr/local/cuda/bin" ~/.bashrc; then
        echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
        echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
    fi
    
    source ~/.bashrc
else
    echo -e "${GREEN}[3/7] CUDA Toolkit 已安装，跳过${NC}"
fi

# 创建项目目录
echo -e "${YELLOW}[4/7] 创建项目目录...${NC}"
PROJECT_DIR="$HOME/vllm-qwen3vl"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 创建虚拟环境
echo -e "${YELLOW}[5/7] 创建 Python 虚拟环境...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 升级 pip
echo -e "${YELLOW}升级 pip...${NC}"
pip install --upgrade pip

# 安装 PyTorch
echo -e "${YELLOW}[6/7] 安装 PyTorch (CUDA 12.4)...${NC}"
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# 安装 vLLM 和其他依赖
echo -e "${YELLOW}[7/7] 安装 vLLM 和相关依赖...${NC}"
pip install vllm==0.11.0
pip install qwen-vl-utils==0.0.14
pip install openai pillow requests

# 验证安装
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  安装完成！${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "验证 PyTorch CUDA 可用性："
python3 -c "import torch; print(f'PyTorch 版本: {torch.__version__}'); print(f'CUDA 可用: {torch.cuda.is_available()}'); print(f'CUDA 版本: {torch.version.cuda}'); print(f'GPU 数量: {torch.cuda.device_count()}')"

echo ""
echo "项目目录: $PROJECT_DIR"
echo ""
echo "使用方法："
echo "  1. 激活环境: source ~/vllm-qwen3vl/venv/bin/activate"
echo "  2. 启动服务: cd ~/vllm-qwen3vl && python server.py"
echo "  3. 在 Windows 中运行 client.py 进行测试"
echo ""

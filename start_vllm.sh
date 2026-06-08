#!/bin/bash
set -e

echo "=========================================="
echo "  vLLM + Qwen3-VL 一键部署 & 启动"
echo "=========================================="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}错误：未检测到 nvidia-smi，请确保已安装 NVIDIA 驱动${NC}"
    exit 1
fi

echo -e "${GREEN}检测到 GPU 信息：${NC}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

PROJECT_DIR="$HOME/vllm"
VENV_DIR="$PROJECT_DIR/venv"
SETUP_FLAG="$PROJECT_DIR/.setup_done"

# 智能选择 pip 镜像源（使用 pip 自身的 whl 文件测试，避免下载大文件）
select_pip_mirror() {
    echo -e "${YELLOW}正在测试 PyPI 镜像源（使用 pip 的 whl 文件进行连通性测试）...${NC}"
    
    # 镜像源列表（名称，URL）
    mirrors=(
        "阿里源|https://mirrors.aliyun.com/pypi/simple"
        "清华源|https://pypi.tuna.tsinghua.edu.cn/simple"
        "腾讯源|https://mirrors.cloud.tencent.com/pypi/simple"
        "华为源|https://mirrors.huaweicloud.com/repository/pypi/simple"
        "中科大源|https://pypi.mirrors.ustc.edu.cn/simple"
        "豆瓣源|https://pypi.douban.com/simple"
    )
    
    # 测试文件：使用 pip 包的一个已知存在的 whl 文件（体积小，约 2MB）
    # 这样既能验证镜像源可用性，又不会消耗太多带宽和时间
    TEST_WHL="pip/pip-24.0-py3-none-any.whl"
    
    SELECTED_MIRROR=""
    SELECTED_NAME=""
    
    for mirror in "${mirrors[@]}"; do
        IFS='|' read -r name url <<< "$mirror"
        echo -e "${BLUE}测试 $name ($url)...${NC}"
        
        # 构建完整的 whl 文件 URL
        whl_url="$url/$TEST_WHL"
        
        # 使用 curl 测试 HEAD 请求，检查文件是否可下载
        if timeout 10 curl -sIL "$whl_url" 2>/dev/null | head -1 | grep -q "200\|302"; then
            echo -e "${GREEN}✓ $name 可用 (能正常下载 whl 文件)${NC}"
            SELECTED_MIRROR="$url"
            SELECTED_NAME="$name"
            break
        else
            echo -e "${RED}✗ $name 不可访问或 whl 下载失败${NC}"
        fi
    done
    
    if [ -n "$SELECTED_MIRROR" ]; then
        echo -e "${GREEN}✓ 选中镜像源: $SELECTED_NAME ($SELECTED_MIRROR)${NC}"
        echo "$SELECTED_MIRROR"
    else
        echo -e "${YELLOW}⚠ 所有镜像源均不可用，将使用官方源（可能较慢）${NC}"
        echo "https://pypi.org/simple"
    fi
}

# 智能选择 apt 镜像源
select_apt_mirror() {
    echo -e "${YELLOW}正在测试 apt 镜像源...${NC}"
    
    UBUNTU_CODENAME=$(lsb_release -cs)
    
    # apt 镜像源列表
    apt_mirrors=(
        "阿里源|http://mirrors.aliyun.com/ubuntu"
        "清华源|http://mirrors.tuna.tsinghua.edu.cn/ubuntu"
        "腾讯源|http://mirrors.cloud.tencent.com/ubuntu"
        "华为源|http://mirrors.huaweicloud.com/ubuntu"
        "中科大源|http://mirrors.ustc.edu.cn/ubuntu"
    )
    
    SELECTED_APT=""
    SELECTED_APT_NAME=""
    
    for mirror in "${apt_mirrors[@]}"; do
        IFS='|' read -r name url <<< "$mirror"
        echo -e "${BLUE}测试 $name ($url)...${NC}"
        
        # 测试能否访问并下载 Packages.gz
        if timeout 10 curl -sIL "$url/dists/$UBUNTU_CODENAME/main/binary-amd64/Packages.gz" 2>/dev/null | head -1 | grep -q "200\|302"; then
            echo -e "${GREEN}✓ $name 可用${NC}"
            SELECTED_APT="$url"
            SELECTED_APT_NAME="$name"
            break
        else
            echo -e "${RED}✗ $name 不可访问或超时${NC}"
        fi
    done
    
    if [ -n "$SELECTED_APT" ]; then
        echo -e "${GREEN}✓ 选中 apt 镜像源: $SELECTED_APT_NAME ($SELECTED_APT)${NC}"
        echo "$SELECTED_APT"
    else
        echo -e "${YELLOW}⚠ 所有 apt 镜像源均不可用，将使用官方源${NC}"
        echo "http://archive.ubuntu.com/ubuntu"
    fi
}

# ---------- 系统环境初始化（仅首次运行） ----------
if [ ! -f "$SETUP_FLAG" ]; then
    echo -e "${YELLOW}[0/6] 智能选择 apt 镜像源...${NC}"
    APT_MIRROR=$(select_apt_mirror)
    
    if [ "$APT_MIRROR" != "http://archive.ubuntu.com/ubuntu" ]; then
        # 备份原配置
        sudo cp /etc/apt/sources.list /etc/apt/sources.list.bak 2>/dev/null || true
        sudo cp /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.bak 2>/dev/null || true
        
        # 配置 apt 镜像源
        if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
            # Ubuntu 24.04+ DEB822 格式
            sudo sed -i "s|URIs:.*|URIs: $APT_MIRROR|g" /etc/apt/sources.list.d/ubuntu.sources
        else
            # 传统格式
            sudo sed -i "s|http://[^ ]*ubuntu|$APT_MIRROR|g" /etc/apt/sources.list
            sudo sed -i "s|http://[^ ]*ubuntu.com/ubuntu|$APT_MIRROR|g" /etc/apt/sources.list
        fi
    fi

    echo -e "${YELLOW}[1/6] 更新系统包...${NC}"
    sudo apt update && sudo apt upgrade -y

    echo -e "${YELLOW}[2/6] 安装基础工具...${NC}"
    sudo apt install -y python3-pip python3-dev python3-venv git curl wget build-essential

    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}Python 版本: $PYTHON_VERSION${NC}"

    # 检查 CUDA 是否已安装
    if ! command -v nvcc &> /dev/null; then
        echo -e "${YELLOW}[3/6] 安装 CUDA Toolkit...${NC}"
        
        cd /tmp
        CUDA_DEB="cuda-repo-wsl-ubuntu-12-8-local_12.8.0-1_amd64.deb"
        if [ ! -f "$CUDA_DEB" ]; then
            wget https://developer.download.nvidia.com/compute/cuda/12.8.0/local_installers/$CUDA_DEB
        fi
        
        sudo dpkg -i $CUDA_DEB
        sudo cp /var/cuda-repo-wsl-ubuntu-12-8-local/cuda-*-keyring.gpg /usr/share/keyrings/ 2>/dev/null || true
        sudo apt-get update
        sudo apt-get -y install cuda-toolkit-12-8
        
        if ! grep -q "/usr/local/cuda/bin" ~/.bashrc; then
            echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
            echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
        fi
        
        # 临时设置环境变量
        export PATH=/usr/local/cuda/bin:$PATH
        export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
    else
        echo -e "${GREEN}CUDA Toolkit 已安装，跳过${NC}"
    fi

    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    echo -e "${YELLOW}[4/6] 智能选择 pip 镜像源（使用 pip whl 文件测试）...${NC}"
    PIP_MIRROR=$(select_pip_mirror)
    
    echo -e "${YELLOW}[5/6] 创建 Python 虚拟环境...${NC}"
    python3 -m venv "$VENV_DIR"
    
    # 激活虚拟环境
    source "$VENV_DIR/bin/activate"
    
    # 升级 pip 并配置选中的镜像源
    pip install --upgrade pip -i "$PIP_MIRROR"
    pip config set global.index-url "$PIP_MIRROR"
    
    echo -e "${GREEN}pip 已配置镜像源: $PIP_MIRROR${NC}"

    echo -e "${YELLOW}[6/6] 安装 PyTorch 和 vLLM...${NC}"
    # 注意：这里才开始真正安装 PyTorch（体积较大，约 2-3GB）
    pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0
    pip install vllm==0.19.1
    pip install qwen-vl-utils==0.0.14
    pip install openai pillow requests
    pip install modelscope

    # ---- 下载模型到本地（仅首次，后续跳过） ----
    MODEL_DIR="$HOME/.cache/modelscope/hub/models/Qwen/Qwen3-VL-2B-Instruct-FP8"
    if [ ! -d "$MODEL_DIR" ]; then
        echo -e "${YELLOW}正在下载模型 Qwen3-VL-2B-Instruct-FP8，约 4.5GB，请耐心等待...${NC}"
        
        # 配置 modelscope 使用国内镜像
        export MODELSCOPE_CACHE="$HOME/.cache/modelscope"
        modelscope download Qwen/Qwen3-VL-2B-Instruct-FP8 --local_dir "$MODEL_DIR"
        
        echo -e "${GREEN}模型下载完成${NC}"
    else
        echo -e "${GREEN}模型已存在，跳过下载${NC}"
    fi

    # 标记环境已就绪
    touch "$SETUP_FLAG"
    
    # 退出虚拟环境
    deactivate
else
    echo -e "${GREEN}环境已就绪，跳过安装步骤${NC}"
    cd "$PROJECT_DIR"
fi

echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  正在启动 vLLM 服务...${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

export PATH="$HOME/.local/bin:$PATH"
export PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=0

# 检查 CUDA 是否可用
python3 -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'" || {
    echo -e "${RED}错误：PyTorch 无法检测到 CUDA${NC}"
    exit 1
}

# 启动 vLLM 服务
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
# PyEasyCon

Nintendo Switch 宝可梦 **火红/叶绿（Gen3）乱数（RNG）狩猎** 自动化工具。

## 快速开始

```bash
pip install -r requirements.txt
python script_rattata.py    # 1号道路 - 草丛 - 小拉达
```

## 硬件要求

| 组件 | 用途 |
|------|------|
| EasyCon 单片机 | 模拟 Switch 手柄按键 |
| 采集卡 | HDMI 画面输入（1920×1080） |
| Nintendo Switch | 运行宝可梦火红/叶绿（Gen3 VC） |

## VL 模型配置

OCR 识别个体值需要 VL 视觉语言模型，编辑 `config/default.yaml` 的 `vl_model` 段，二选一：

### 方案 A：免费云端 GLM-4.6V-Flash（无需 GPU，需联网）

1. 注册 [智谱 AI 开放平台](https://bigmodel.cn/apikey/platform)，创建 API Key
2. 编辑 `config/default.yaml`：

```yaml
# config/default.yaml
vl_model:
  type: glm
  glm:
    model: "glm-4.6v-flash"
    api_key: "你的APIKey"
```

### 方案 B：本地 vLLM + Qwen3-VL-2B（建议 NVIDIA GPU ≥ 6 GB，无需联网）

1. 在 WSL Ubuntu 中部署 vLLM，使用 `vllm/` 目录下的脚本：
   - [`setup_wsl.sh`](vllm/setup_wsl.sh) — 安装 CUDA、PyTorch、vLLM
   - [`download_model.py`](vllm/download_model.py) — 下载模型
   - [`start_vllm.sh`](vllm/start_vllm.sh) — 启动服务（复制到 `~/vllm-qwen3vl/`）
2. 双击 `start_vllm.bat` 或在终端运行 `start_vllm.ps1`

```yaml
# config/default.yaml
vl_model:
  type: vllm          # 默认
  vllm:
    base_url: "http://localhost:8000/v1"
```

## 运行脚本

在以下示例脚本基础上修改，设定乱数目标：

| 脚本 | 位置 | 方式 | 目标 |
|------|------|------|------|
| `script_rattata.py` | Route 22 | 草丛 | 小拉达 |
| `script_spearow.py` | Route 22 | 草丛 | 烈雀 |
| `script_mankey.py` | Route 22 | 草丛 | 猴怪 |
| `script_gyarados.py` | Route 22 | 超级钓竿 | 暴鲤龙 |
| `script_poliwag.py` | Route 22 | 超级钓竿 | 蚊香蝌蚪 |
| `script_porygon.py` | Game Corner | 定点 | 3D龙 |

每个脚本自动完成：**尝试命中乱数帧 → 捕获/兑换精灵 → OCR获取精灵信息 → 反查校准 → 循环至闪光**。

## 项目结构

```
PyEasyCon/
├── config/default.yaml     # 配置文件（VL 模型、采集卡、ROI 等）
├── gui/                    # Pygame 图形界面
├── easycon/                # EasyCon 协议 & 图像识别
├── vision/                 # VL 模型 OCR & 精灵匹配
├── rng/                    # tenlines RNG 引擎（C++ pybind）
├── scripts/                # 公共子流程（hit/capture/calibration）
├── modules/                # GUI 面板组件
├── assets/                 # 精灵图 & 标签资源
├── vllm/                   # vLLM 部署脚本
├── script_*.py             # 各宝可梦狩猎脚本
├── start_vllm.ps1/.bat     # vLLM 一键启动
└── requirements.txt
```

## License

MIT

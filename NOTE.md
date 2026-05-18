# EasyCon 项目架构分析笔记

> 生成日期: 2026-05-16

---

## 一、项目概述

**EasyCon** 是一个基于 Python 的宝可梦自动化工具，主要用于 Nintendo Switch 上宝可梦火红/叶绿（Gen3）的 **RNG（乱数）狩猎**。核心流程是：

1. 通过 **EasyCon 单片机** 模拟 Switch 手柄输入，精确控制按键时序
2. 通过 **采集卡** 获取游戏画面（1920×1080）
3. 使用 **VL 模型（vLLM/GLM）** 进行 OCR 识别宝可梦的个体值、性格等信息
4. 使用 **OpenCV 模板匹配** 识别画面中的宝可梦精灵和 UI 元素
5. 通过 **RNG 算法（tenlines）** 反查实际命中的 seed/advances，自动校准偏差

---

## 二、目录结构总览

```
EasyCon-release/
├── easycon_api.py          # 核心 API：单片机通信 + Switch 手柄协议 + 图像识别
├── gui.py                  # 主 GUI 应用（Pygame）+ 模块级 API 函数
├── demo_script.py          # RNG 狩猎脚本（用户实际运行的脚本）
├── calibration.py          # 反查校准模块（根据 OCR 数据计算 seed/adv 偏差）
├── convert_to_il.py        # 工具：GBA 精灵图 → .IL 标签文件
├── .gitignore
│
├── modules/                # 功能模块
│   ├── __init__.py          # 导出 GUI 四大面板组件
│   ├── video_module.py      # 视频采集与显示模块
│   ├── label_maker.py       # 图像标签制作模块
│   ├── script_editor.py     # 脚本编辑器（语法高亮）
│   ├── output_panel.py      # 运行日志输出面板
│   ├── pokemon_ocr.py       # VL 模型 OCR（vLLM/GLM 双后端）
│   ├── pokemon_sprite.py    # 宝可梦精灵图模板匹配
│   ├── species_zh.py        # 宝可梦英→中译名字典
│   │
│   ├── tenlines/            # RNG 计算引擎（C++ ten-lines 的 Python 移植）
│   │   ├── __init__.py
│   │   ├── tenlines.py      # 核心 RNG 算法（LCRNG、seed 恢复、搜索）
│   │   ├── tenlines_utils.py # Python 封装（物种数据、遇敌表、IV 计算器）
│   │   ├── src/pybind/      # C++ pybind11 绑定（性能关键路径）
│   │   └── resources/       # 游戏数据文件
│   │       ├── fr_eng_nx.bin
│   │       ├── Personal/Gen3/personal_rsefrlg.bin
│   │       ├── i18n/en/species_en.txt, abilities_en.txt
│   │       └── EncounterTables/Gen3/frlg/wild_encounters.json
│   │
│   └── appearance/          # 宝可梦精灵图资源
│       ├── normal/          # 普通配色精灵图（PNG, ~330 张）
│       ├── shiny/           # 异色配色精灵图
│       ├── resources/       # 原始素材（来自 pret/pokefirered）
│       ├── generate_appearance.py  # 从原始素材生成精灵图
│       └── download_resources.py   # 下载原始素材
│
├── labels/                  # UI 元素图像标签（.IL 文件, ~150 个）
│   ├── 3代关键词*.IL        # 游戏 UI 关键词标签
│   ├── 3代普通*.IL          # 普通宝可梦外观标签
│   ├── NS主页*.IL           # Switch 主页标签
│   └── 叶绿/火红老虎机*.IL  # 老虎机标签
│
└── ImgLabel-FRLG/           # 宝可梦精灵图标签（.IL 文件, ~200 个）
    └── frlg_{id}_{name}.IL  # 用于 MaskedSqDiffNormed 匹配
```

---

## 三、逻辑功能模块分析

### 3.1 硬件控制层

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| [easycon_api.py](file:///c:/Users/章健飞/projects/EasyCon-release/easycon_api.py) | 单片机串口通信、Switch 手柄协议、按键/摇杆控制 | ~700 |

**核心类：**
- `GamePadKey` / `SwitchButton` / `SwitchHAT` — 按键枚举定义
- `SwitchReport` — 手柄状态报告（序列化为协议字节）
- `EasyConController` — 主控制器（连接、按键、摇杆、延迟）
- `ImageRecognizer` — 图像识别器（采集卡 + 模板匹配）
- `ImgLabel` — 图像标签数据结构

**问题：** 一个文件混合了 3 个职责：串口通信协议、手柄控制、图像识别。

### 3.2 GUI 层

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| [gui.py](file:///c:/Users/章健飞/projects/EasyCon-release/gui.py) | 主 GUI + 脚本执行引擎 + 模块级 API | ~820 |

**核心类：**
- `EasyConGUI` — 主 GUI 类，整合所有模块

**GUI 布局（4 面板）：**
```
┌─────────────────────┬──────────────┐
│  游戏画面 (Video)    │ 标签制作      │
│  640×360            │ (LabelMaker) │
├─────────────────────┤              │
│  脚本编辑器          ├──────────────┤
│  (ScriptEditor)     │ 运行输出      │
│  640×400            │ (OutputPanel)│
└─────────────────────┴──────────────┘
```

**模块级 API 函数（供脚本 `from gui import ...`）：**
`press`, `hold`, `release`, `lstick`, `capture`, `wait`, `log`, `search_label`, `get_frame`, `is_running`, `ocr_pokemon`, `ocr_elevated`, `ocr_caught_info`, `ocr_caught_iv`, `ocr_custom`, `identify_pokemon`, `ocr_name`, `run_script`

**问题：** `gui.py` 是典型的"上帝类"，包含了 GUI 渲染、脚本执行、OCR 代理、标签搜索、模块级 API 等所有职责。

### 3.3 GUI 子模块

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| [video_module.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/video_module.py) | 采集卡视频捕获、键盘映射、画面渲染 | ~300 |
| [label_maker.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/label_maker.py) | 截图、框选 ROI、保存/加载 .IL 标签 | ~400 |
| [script_editor.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/script_editor.py) | Python 代码编辑器（pygments 语法高亮） | ~400 |
| [output_panel.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/output_panel.py) | 日志输出面板（带时间戳、颜色分类） | ~90 |

### 3.4 视觉识别层

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| [pokemon_ocr.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/pokemon_ocr.py) | VL 模型 OCR（vLLM 本地 / GLM 在线双后端） | ~600 |
| [pokemon_sprite.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/pokemon_sprite.py) | 精灵图模板匹配（OpenCV TM_SQDIFF_NORMED + mask） | ~200 |

**pokemon_ocr.py 核心能力：**
- 屏幕类型分类（ELEVATED / CAUGHT_INFO / CAUGHT_IV / UNKNOWN）— 基于 HSV 颜色比例
- 并行 OCR（ThreadPoolExecutor）识别等级、6 项个体值、性格、特性、性别
- 双 VL 后端：本地 vLLM（Qwen3-VL-2B）+ 在线 GLM-4.6v（带速率限制重试）
- 自定义 OCR 接口（`ocr_custom`）

**pokemon_sprite.py 核心能力：**
- GBA 画面区域自动检测（`detect_gba_area`）
- 精灵图缓存 + 多形态支持（如 #351 飘浮泡泡 4 形态）
- 异色检测（对比 normal/shiny 两套精灵图匹配分数）

### 3.5 RNG 计算层

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| [tenlines.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/tenlines/tenlines.py) | 核心 RNG 算法（LCRNG、seed 恢复、wild/static 搜索、校准） | ~800 |
| [tenlines_utils.py](file:///c:/Users/章健飞/projects/EasyCon-release/modules/tenlines/tenlines_utils.py) | Python 封装（物种数据、遇敌表、IV 计算器、GameSettings） | ~400 |
| [calibration_bind.cpp](file:///c:/Users/章健飞/projects/EasyCon-release/modules/tenlines/src/pybind/calibration_bind.cpp) | C++ pybind11 绑定（性能关键路径） | — |

**核心算法：**
- LCRNG（线性同余随机数生成器）：`pokerng_next`, `pokerngr_next`, `pokerng_jump`
- Seed 恢复：从 IV 反推 seed（Method 1/2/4）
- Wild/Static 搜索：根据目标 IV 搜索匹配的 seed
- 校准：根据 OCR 观测反查实际 seed/advances 偏移

### 3.6 脚本层

| 文件 | 功能 | 行数(约) |
|------|------|----------|
| [demo_script.py](file:///c:/Users/章健飞/projects/EasyCon-release/demo_script.py) | RNG 狩猎主脚本 | ~480 |
| [calibration.py](file:///c:/Users/章健飞/projects/EasyCon-release/calibration.py) | 反查校准模块 | ~280 |

**demo_script.py 核心流程：**
```
main() 循环:
  1. hit_init_seed()    — 精确时序按键命中目标 seed
  2. hit_tv_frame()     — TV 模式消耗帧数
  3. hit_super_rod() / hit_sweet_scent() / hit_gift() — 遇敌操作
  4. check_shiny()      — 精灵图匹配检测是否异色
  5. catch_with_ball()  — 自动捕获
  6. record_for_finetune() — OCR 记录 + 喂糖缩小 IV 范围
  7. run_calibration()  — 定期反查校准偏差
  8. restart()          — 重启游戏
```

### 3.7 数据资源层

| 目录/文件 | 内容 |
|-----------|------|
| `labels/` | ~150 个 UI 元素标签（.IL JSON 格式，含 base64 图片） |
| `ImgLabel-FRLG/` | ~200 个宝可梦精灵标签（用于 MaskedSqDiffNormed 匹配） |
| `modules/appearance/normal/` | ~330 张普通配色精灵图（64×64 RGBA PNG） |
| `modules/appearance/shiny/` | ~330 张异色配色精灵图 |
| `modules/tenlines/resources/` | 游戏数据（personal.bin, species_en.txt, encounters.json, seed.bin） |
| `modules/species_zh.py` | 386 只宝可梦的英→中译名字典 |

---

## 四、依赖关系图

```
demo_script.py
  ├── gui.py (模块级 API: press, wait, log, search_label, ocr_pokemon, ...)
  │     ├── easycon_api.py (EasyConController, GamePadKey)
  │     ├── modules/video_module.py (采集卡画面)
  │     ├── modules/label_maker.py (标签制作)
  │     ├── modules/script_editor.py (代码编辑)
  │     ├── modules/output_panel.py (日志输出)
  │     ├── modules/pokemon_ocr.py (VL OCR)
  │     └── modules/pokemon_sprite.py (精灵匹配)
  ├── calibration.py
  │     └── modules/tenlines/tenlines_utils.py (calibration API, IV calculator)
  │           └── modules/tenlines/tenlines.py (核心 RNG 算法)
  └── modules/tenlines/tenlines_utils.py (GameSettings, get_seed_time, ...)

convert_to_il.py
  ├── modules/pokemon_sprite.py (精灵图加载)
  └── modules/tenlines/tenlines_utils.py (物种名称)
```

---

## 五、现有架构问题

### 5.1 上帝类问题（God Class）

`gui.py` 中的 `EasyConGUI` 类承担了过多职责：
- GUI 渲染与事件分发
- 脚本执行引擎（`_run_script`, `_stop_script`）
- 控制器初始化与连接管理
- VL 模型状态检测
- 标签搜索（`search_label` 方法 ~100 行）
- OCR 代理方法（`_ocr_pokemon`, `_ocr_elevated`, ...）
- 模块级 API 函数（全局 `_current_gui` 单例）

### 5.2 模块级 API 的脆弱性

```python
# gui.py 底部
_current_gui = None  # 全局单例

def press(button, duration_ms=50):
    if _current_gui:
        _current_gui.press(button, duration_ms)
```

这种模式的问题：
- 隐式依赖全局状态，测试困难
- 脚本必须 `from gui import press`，与 GUI 强耦合
- 无法在无 GUI 环境（如纯 CLI）下运行脚本

### 5.3 职责混合

`easycon_api.py` 混合了 3 个不同关注点：
- 串口通信协议（`EzDvCommand`, `Reply`）
- Switch 手柄协议（`SwitchReport`, `SwitchButton`, `SwitchHAT`）
- 图像识别（`ImageRecognizer`, `ImgLabel`）

### 5.4 硬编码与配置分散

- 采集卡分辨率 1920×1080 硬编码在多处
- ROI 坐标硬编码在 `pokemon_ocr.py`
- GBA 区域偏移硬编码在 `pokemon_sprite.py` 和 `convert_to_il.py`
- 串口波特率、超时等硬编码在 `easycon_api.py`
- 脚本参数（SEED_HEX, ADVANCES, TRAINER_ID 等）直接写在 `demo_script.py` 顶部

### 5.5 紧耦合

- `demo_script.py` 直接 import `gui` 模块级函数，无法独立测试
- `calibration.py` 直接依赖 `modules.tenlines.tenlines_utils`
- `video_module.py` 直接 import `easycon_api` 的 `EasyConController`
- GUI 模块之间通过 `EasyConGUI` 直接引用彼此

### 5.6 缺少抽象层

- 没有统一的"脚本执行上下文"接口
- 没有"视频源"抽象（目前直接耦合 OpenCV VideoCapture）
- 没有"识别器"抽象（OCR 和精灵匹配是两套独立接口）
- 没有配置管理系统

### 5.7 文件组织问题

- `labels/` 和 `ImgLabel-FRLG/` 两个标签目录平级放在根目录，语义不清
- `modules/appearance/` 包含大量 PNG 资源文件，与 Python 代码混合
- `modules/tenlines/` 包含 C++ 源码、编译产物、Python 代码、资源文件，结构复杂
- `demo_script.py` 和 `calibration.py` 放在根目录，与 `gui.py` 同级但职责不同

---

## 六、重构建议

### 6.1 推荐的目标目录结构

```
EasyCon-release/
├── easycon/                        # 核心库（纯 Python，无 GUI 依赖）
│   ├── __init__.py
│   ├── controller.py               # EasyConController（从 easycon_api.py 拆分）
│   ├── protocol.py                 # Switch 手柄协议（SwitchReport, SwitchButton, ...）
│   ├── serial_transport.py         # 串口通信层（EzDvCommand, Reply）
│   ├── image_label.py              # ImgLabel 数据结构
│   ├── recognizer.py               # ImageRecognizer（图像模板匹配）
│   └── capture.py                  # 采集卡抽象（VideoCapture 封装）
│
├── vision/                         # 视觉识别模块
│   ├── __init__.py
│   ├── ocr.py                      # VL OCR（从 pokemon_ocr.py 迁移）
│   ├── sprite_matcher.py           # 精灵图匹配（从 pokemon_sprite.py 迁移）
│   ├── screen_classifier.py        # 屏幕类型分类
│   └── roi_config.py               # ROI 坐标配置（集中管理）
│
├── rng/                            # RNG 计算模块
│   ├── __init__.py
│   ├── lcrng.py                    # LCRNG 核心算法
│   ├── searcher.py                 # Wild/Static 搜索
│   ├── calibration.py              # 校准逻辑
│   ├── species.py                  # 物种数据（从 species_zh.py + tenlines_utils 合并）
│   ├── encounters.py               # 遇敌表
│   └── resources/                  # 游戏数据文件
│
├── gui/                            # GUI 应用
│   ├── __init__.py
│   ├── app.py                      # EasyConGUI 主类（精简后）
│   ├── panels/
│   │   ├── __init__.py
│   │   ├── video_panel.py          # 视频面板
│   │   ├── label_panel.py          # 标签制作面板
│   │   ├── editor_panel.py         # 脚本编辑器面板
│   │   └── output_panel.py         # 输出面板
│   └── script_engine.py            # 脚本执行引擎（从 gui.py 拆分）
│
├── scripts/                        # 用户脚本目录
│   ├── demo_rng_hunt.py            # RNG 狩猎脚本（原 demo_script.py）
│   └── ...
│
├── assets/                         # 静态资源（统一管理）
│   ├── labels/                     # UI 标签（原 labels/）
│   ├── sprite_labels/              # 精灵标签（原 ImgLabel-FRLG/）
│   └── sprites/                    # 精灵图（原 modules/appearance/）
│       ├── normal/
│       ├── shiny/
│       └── resources/
│
├── tools/                          # 工具脚本
│   ├── convert_to_il.py
│   ├── download_sprites.py
│   └── generate_sprites.py
│
├── config/                         # 配置文件
│   ├── default.yaml                # 默认配置
│   └── ...
│
├── .env                            # 环境变量（VL API key 等）
├── .gitignore
└── README.md
```

### 6.2 关键重构步骤

#### 第一步：引入脚本执行上下文（ScriptContext）

替代全局 `_current_gui` 单例模式：

```python
# easycon/context.py
class ScriptContext:
    """脚本执行上下文，解耦脚本与 GUI"""
    def __init__(self, controller, capture, recognizer, ocr, logger):
        self.controller = controller
        self.capture = capture
        self.recognizer = recognizer
        self.ocr = ocr
        self.logger = logger
    
    def press(self, button, duration_ms=50): ...
    def wait(self, ms): ...
    def search_label(self, name, threshold=80): ...
    def ocr_pokemon(self): ...
    # ...
```

脚本变为：
```python
# scripts/demo_rng_hunt.py
def main(ctx: ScriptContext):
    while ctx.is_running():
        ctx.press('A')
        # ...
```

#### 第二步：拆分 easycon_api.py

```
easycon_api.py (700行)
  → easycon/protocol.py       (~200行) Switch 手柄协议
  → easycon/serial_transport.py (~150行) 串口通信
  → easycon/controller.py     (~200行) EasyConController
  → easycon/recognizer.py     (~150行) ImageRecognizer
  → easycon/image_label.py    (~50行)  ImgLabel
```

#### 第三步：拆分 gui.py

```
gui.py (820行)
  → gui/app.py              (~200行) 主窗口 + 模块组装
  → gui/script_engine.py    (~150行) 脚本执行逻辑
  → gui/panels/video_panel.py   (从 video_module.py 迁移)
  → gui/panels/label_panel.py   (从 label_maker.py 迁移)
  → gui/panels/editor_panel.py  (从 script_editor.py 迁移)
  → gui/panels/output_panel.py  (从 output_panel.py 迁移)
```

#### 第四步：统一配置管理

```yaml
# config/default.yaml
capture:
  resolution: [1920, 1080]
  device_id: 0
  backend: dshow

serial:
  baudrate: 115200
  timeout: 2.0

vision:
  roi:
    elevated_level: [360, 876, 138, 124]
    elevated_stats: [[1545, 48, 152, 97], ...]
    # ...
  gba:
    offset_x: 180
    offset_y: 5
    scale: 6.5

vl_model:
  type: vllm  # vllm | glm
  vllm_url: "http://localhost:8000/v1"
  glm_model: "glm-4.6v-flash"
```

#### 第五步：引入依赖注入

```python
# gui/app.py
class EasyConApp:
    def __init__(self):
        config = load_config()
        self.controller = EasyConController(config.serial)
        self.capture = VideoCapture(config.capture)
        self.recognizer = ImageRecognizer(config.vision)
        self.ocr = VLMOcr(config.vl_model)
        self.ctx = ScriptContext(
            controller=self.controller,
            capture=self.capture,
            recognizer=self.recognizer,
            ocr=self.ocr,
            logger=self.output_panel,
        )
```

### 6.3 优先级建议

| 优先级 | 重构项 | 收益 | 风险 |
|--------|--------|------|------|
| **高** | 引入 ScriptContext，消除全局单例 | 脚本可独立测试、CLI 运行 | 中 |
| **高** | 拆分 easycon_api.py | 职责清晰、可复用 | 低 |
| **高** | 统一配置管理（YAML/JSON） | 消除硬编码 | 低 |
| **中** | 拆分 gui.py 上帝类 | 可维护性大幅提升 | 中 |
| **中** | 统一 assets/ 资源目录 | 结构清晰 | 低 |
| **中** | 视觉识别模块独立为 vision/ | 关注点分离 | 中 |
| **低** | RNG 模块独立为 rng/ | 可独立发布为库 | 低 |
| **低** | 引入依赖注入容器 | 可测试性 | 高 |

---

## 七、技术栈总结

| 层级 | 技术 |
|------|------|
| GUI 框架 | Pygame |
| 视频采集 | OpenCV (cv2.VideoCapture + CAP_DSHOW) |
| 图像处理 | OpenCV (模板匹配、颜色分析) |
| VL OCR | vLLM (Qwen3-VL-2B 本地) / GLM-4.6v (在线 API) |
| 串口通信 | pyserial |
| RNG 计算 | Python 纯计算 + C++ pybind11 绑定 |
| 精灵图处理 | PIL/Pillow |
| 语法高亮 | Pygments |
| 配置管理 | 无（目前硬编码 + .env） |

---

## 八、关键数据流

```
采集卡 → VideoCapture → 1920×1080 BGR Frame
  │
  ├─→ VideoModule (Pygame 渲染显示)
  ├─→ LabelMaker (截图 → 框选 ROI → 保存 .IL)
  ├─→ search_label (模板匹配 → 匹配度)
  ├─→ pokemon_ocr (VL 模型 OCR → 个体值/性格/特性)
  ├─→ pokemon_sprite (精灵图匹配 → species_id + 异色判定)
  │
  └─→ demo_script.py 主循环:
       1. 按键时序控制 (EasyConController → 单片机 → Switch)
       2. 画面检测 (search_label 判断 UI 状态)
       3. 精灵识别 (pokemon_sprite 判断异色)
       4. OCR 记录 (pokemon_ocr → JSON 日志)
       5. 反查校准 (calibration.py → tenlines RNG 计算)
       6. 重启循环
```

---

*此文档基于 2026-05-16 的项目代码分析生成，后续重构时可同步更新。*
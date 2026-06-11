"""
Pokemon OCR Module - 宝可梦信息 OCR 识别模块
通过 OpenAI 兼容 API 调用 VL 模型进行图像识别，提供给 EasyCon 脚本使用

ROI 坐标基于 1920×1080 (采集卡直出)

配置来源：default.yaml → vl_model 段
"""

import base64
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

# ==================== VL 模型配置（default.yaml → vl_model 段） ====================

def read_vl_config():
    """读取 VL 模型配置（延迟导入，避免循环依赖）"""
    try:
        from easycon.config import get
        return get("vl_model", {})
    except Exception:
        return {}

# ==================== 模型提供者注册表 ====================

MODEL_TYPE_VLLM = "vllm"
MODEL_TYPE_OLLAMA = "ollama"
MODEL_TYPE_SILICONFLOW = "siliconflow"


@dataclass
class ModelProvider:
    """统一的模型提供者描述，消除 vLLM/Ollama/SiliconFlow 三套重复逻辑"""
    key: str                                    # "vllm" / "ollama" / "siliconflow"
    display: str                                # "vLLM" / "Ollama" / "SiliconFlow"
    base_url: str
    api_key: str
    model_name: str
    max_retries: int = 1                        # API 调用最大重试次数
    max_concurrency: int = 8                    # 并行 OCR 时的最大线程数
    client_ref: Optional[object] = field(default=None, repr=False, init=False)


def normalize_host(url: str) -> str:
    """将 URL 中的 0.0.0.0 替换为 127.0.0.1，因为 0.0.0.0 是服务器 bind 地址，无法作为客户端连接地址"""
    return url.replace("0.0.0.0", "127.0.0.1")


def build_providers() -> Dict[str, ModelProvider]:
    """从配置文件构建模型提供者注册表"""
    cfg = read_vl_config()

    vllm_cfg = cfg.get("vllm", {})
    ollama_cfg = cfg.get("ollama", {})
    sf_cfg = cfg.get("siliconflow", {})

    return {
        MODEL_TYPE_VLLM: ModelProvider(
            key=MODEL_TYPE_VLLM, display="vLLM",
            base_url=normalize_host(vllm_cfg.get("base_url", "http://localhost:8000/v1")),
            api_key=vllm_cfg.get("api_key", "sk-PyEasyCon"),
            model_name=vllm_cfg.get("model_name", "Qwen3-VL-2B-Instruct-FP8"),
            max_concurrency=8,
        ),
        MODEL_TYPE_OLLAMA: ModelProvider(
            key=MODEL_TYPE_OLLAMA, display="Ollama",
            base_url=normalize_host(ollama_cfg.get("base_url", "http://localhost:8008/v1")),
            api_key=ollama_cfg.get("api_key", "sk-PyEasyCon"),
            model_name=ollama_cfg.get("model_name", "modelscope.cn/Qwen/Qwen3-VL-2B-Instruct-GGUF:latest"),
            max_concurrency=4,
        ),
        MODEL_TYPE_SILICONFLOW: ModelProvider(
            key=MODEL_TYPE_SILICONFLOW, display="SiliconFlow",
            base_url=normalize_host(sf_cfg.get("base_url", "https://api.siliconflow.cn/v1")),
            api_key=sf_cfg.get("api_key", ""),
            # 兼容 config 中同时使用 model 和 model_name 两种 key
            model_name=sf_cfg.get("model") or sf_cfg.get("model_name", "Qwen/Qwen3-VL-8B-Instruct"),
            max_retries=sf_cfg.get("max_retries", 3),
            max_concurrency=4,
        ),
    }


PROVIDERS = build_providers()

# 兼容旧代码的模块级常量（从注册表派生，保证调用方不受影响）
VLLM_MODEL_NAME = PROVIDERS[MODEL_TYPE_VLLM].model_name
OLLAMA_MODEL_NAME = PROVIDERS[MODEL_TYPE_OLLAMA].model_name
SILICONFLOW_MODEL = PROVIDERS[MODEL_TYPE_SILICONFLOW].model_name


def get_provider(key: str) -> ModelProvider:
    """获取指定 key 的提供者，key 无效时回退到 vllm"""
    return PROVIDERS.get(key, PROVIDERS[MODEL_TYPE_VLLM])


# ==================== 当前模型状态 ====================

vl_cfg = read_vl_config()
preferred_model = vl_cfg.get("type", "vllm").lower()
current_model_type = preferred_model if preferred_model in PROVIDERS else MODEL_TYPE_VLLM

model_init_done = False
model_init_lock = threading.Lock()

openai_available = False
try:
    from openai import OpenAI
    openai_available = True
except ImportError:
    pass

# SiliconFlow 并发控制（API 侧有速率限制）
siliconflow_semaphore = threading.Semaphore(2)


# ==================== ROI 定义 (1920×1080) ====================

ROI = Tuple[int, int, int, int]
# Appeared 界面: 宝可梦种类
APPEARED_NAME_RECT = (300, 135, 400, 55)
# Elevated 界面: 等级位于左下
ELEVATED_LEVEL_RECT: ROI = (360, 876, 138, 124)
# Elevated 界面: 6项能力值，右侧纵列 (hp, attack, defense, sp_atk, sp_def, speed)
ELEVATED_STAT_RECTS: List[ROI] = [
    (1545, 48, 152, 97),    # hp
    (1545, 145, 152, 97),   # attack
    (1545, 242, 152, 97),   # defense
    (1545, 339, 152, 97),   # sp_atk
    (1545, 436, 152, 97),   # sp_def
    (1545, 533, 152, 97),   # speed
]

# Caught 界面: 等级 (左上)
CAUGHT_LEVEL_RECT: ROI = (262, 124, 108, 85)
# Caught 界面: 性别符号 (中上)
CAUGHT_GENDER_RECT: ROI = (847, 124, 68, 81)
# Caught IV 界面: HP 能力值 (右侧)
CAUGHT_STAT_HP_RECT: ROI = (1439, 140, 288, 72)
# Caught IV 界面: 其余5项能力值 (右侧纵列)
CAUGHT_STAT_OTHER_RECTS: List[ROI] = [
    (1600, 258, 127, 72),   # attack
    (1600, 343, 127, 72),   # defense
    (1600, 429, 127, 72),   # sp_atk
    (1600, 514, 127, 72),   # sp_def
    (1600, 599, 127, 72),   # speed
]
# Caught IV 界面: 特性 (底部中)
CAUGHT_ABILITY_RECT: ROI = (635, 853, 529, 78)
# Caught Info 界面: 性格 (中下)
CAUGHT_NATURE_RECT: ROI = (222, 746, 741, 97)

# 屏幕类型
SCREEN_ELEVATED = "ELEVATED"
SCREEN_CAUGHT_INFO = "CAUGHT_INFO"
SCREEN_CAUGHT_IV = "CAUGHT_IV"
SCREEN_UNKNOWN = "UNKNOWN"

# 25种性格
NATURES = [
    "Adamant", "Bashful", "Bold", "Brave", "Calm", "Careful", "Docile",
    "Gentle", "Hardy", "Hasty", "Impish", "Jolly", "Lax", "Lonely",
    "Mild", "Modest", "Naive", "Naughty", "Quiet", "Quirky", "Rash",
    "Relaxed", "Sassy", "Serious", "Timid"
]


def get_all_roi_boxes() -> List[Dict]:
    """
    返回所有 1920×1080 ROI 框的元数据，供 GUI 叠加绘制。

    每个元素: { 'label': str, 'roi': (x,y,w,h), 'color': (r,g,b), 'group': str }
    """
    stat_labels = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe']
    boxes = []

    # Elevated
    boxes.append({'label': 'Lv', 'roi': ELEVATED_LEVEL_RECT, 'color': (255, 255, 0), 'group': 'Elevated'})
    for i in range(6):
        boxes.append({'label': f'IV {stat_labels[i]}', 'roi': ELEVATED_STAT_RECTS[i], 'color': (255, 255, 0), 'group': 'Elevated'})

    # Caught Info
    boxes.append({'label': 'Lv', 'roi': CAUGHT_LEVEL_RECT, 'color': (0, 255, 255), 'group': 'Caught'})
    boxes.append({'label': 'Gender', 'roi': CAUGHT_GENDER_RECT, 'color': (0, 255, 255), 'group': 'Caught'})
    boxes.append({'label': 'Nature', 'roi': CAUGHT_NATURE_RECT, 'color': (0, 255, 255), 'group': 'Caught'})

    # Caught IV
    boxes.append({'label': 'HP', 'roi': CAUGHT_STAT_HP_RECT, 'color': (255, 0, 255), 'group': 'CaughtIV'})
    for i in range(5):
        boxes.append({'label': f'IV {stat_labels[i+1]}', 'roi': CAUGHT_STAT_OTHER_RECTS[i], 'color': (255, 0, 255), 'group': 'CaughtIV'})
    boxes.append({'label': 'Ability', 'roi': CAUGHT_ABILITY_RECT, 'color': (255, 0, 255), 'group': 'CaughtIV'})

    # Appeared
    boxes.append({'label': 'Name', 'roi': APPEARED_NAME_RECT, 'color': (0, 255, 0), 'group': 'Appeared'})

    return boxes


# ==================== VL 客户端 & 服务检测（统一层） ====================

def get_client_ref(provider_key: str) -> OpenAI:
    """获取指定提供者的 OpenAI 客户端"""
    if not openai_available:
        raise ImportError("openai 库未安装，请运行: pip install openai")
    provider = get_provider(provider_key)
    if provider.client_ref is None:
        provider.client_ref = OpenAI(api_key=provider.api_key, base_url=provider.base_url, timeout=60)
    return provider.client_ref


def probe_ollama_native(host: str, timeout: float = 5) -> bool:
    """通过 Ollama 原生 API (/api/tags) 探测服务，比 /v1/models 更可靠（模型加载期间也立即可用）"""
    import urllib.request
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def probe_service(provider_key: str, timeout: float = 5) -> bool:
    """探测指定模型提供者服务是否可用"""
    if not openai_available:
        return False
    try:
        provider = get_provider(provider_key)
        # Ollama 使用原生 API 探测，避免模型加载期间 /v1/models 不可用
        if provider_key == MODEL_TYPE_OLLAMA:
            host = provider.base_url.rstrip('/').removesuffix('/v1')
            return probe_ollama_native(host, timeout)
        client = OpenAI(api_key=provider.api_key, base_url=provider.base_url, timeout=timeout)
        models = client.models.list()
        return len(models.data) > 0
    except Exception:
        return False


def probe_all_services(types_to_probe: List[str] = None) -> Dict[str, bool]:
    """并行探测多个模型服务，返回 {provider_key: is_available}"""
    if types_to_probe is None:
        types_to_probe = list(PROVIDERS.keys())
    results = {}

    def probe_one(key):
        results[key] = probe_service(key)

    with ThreadPoolExecutor(max_workers=len(types_to_probe)) as ex:
        list(ex.map(probe_one, types_to_probe))
    return results


# ==================== 公开的服务检测 API ====================

def check_service() -> bool:
    """检测当前模型类型是否可用"""
    return probe_service(current_model_type)


def check_vllm_service() -> bool:
    return probe_service(MODEL_TYPE_VLLM)


def check_ollama_service() -> bool:
    return probe_service(MODEL_TYPE_OLLAMA)


def check_siliconflow_service() -> bool:
    return probe_service(MODEL_TYPE_SILICONFLOW)


def get_available_model_types() -> list:
    """并行探测所有模型服务，返回可用的模型类型列表"""
    probe_results = probe_all_services()
    return [k for k, available in probe_results.items() if available]


def set_model_type(model_type: str):
    global current_model_type
    if model_type not in PROVIDERS:
        raise ValueError(f"不支持的模型类型: {model_type}，支持的类型: {list(PROVIDERS.keys())}")
    current_model_type = model_type


def get_current_model_type() -> str:
    return current_model_type


def get_vllm_model() -> str:
    """获取 vLLM 模型名称（兼容旧调用方）"""
    return VLLM_MODEL_NAME


# ==================== 画面预处理 (1920×1080 直入) ====================

SRC_WIDTH = 1920
SRC_HEIGHT = 1080


# ==================== 屏幕类型分类 ====================

def classify_screen_type(game_screen: np.ndarray, debug: bool = False) -> str:
    if game_screen is None:
        return SCREEN_UNKNOWN
    h, w = game_screen.shape[:2]
    hsv = cv2.cvtColor(game_screen, cv2.COLOR_BGR2HSV)
    area = h * w

    def ratio(lower, upper):
        return np.sum(cv2.inRange(hsv, np.array(lower), np.array(upper)) > 0) / area

    white_ratio = ratio([0, 0, 200], [180, 30, 255])
    blue_ratio = ratio([90, 50, 50], [130, 255, 255])
    cyan_ratio = ratio([85, 50, 50], [95, 255, 255])
    blue_cyan = blue_ratio + cyan_ratio
    yellow_ratio = ratio([20, 50, 50], [35, 255, 255])

    if debug:
        print(f"[classify] size={w}x{h} white={white_ratio:.4f} blue={blue_ratio:.4f} cyan={cyan_ratio:.4f} blue_cyan={blue_cyan:.4f} yellow={yellow_ratio:.4f}")

    if blue_cyan > 0.15:
        return SCREEN_ELEVATED
    if yellow_ratio > 0.15:
        return SCREEN_CAUGHT_IV
    if white_ratio > 0.35:
        return SCREEN_CAUGHT_INFO
    return SCREEN_UNKNOWN


# ==================== VLM OCR 调用 ====================

def image_to_base64(image: np.ndarray) -> str:
    _, buffer = cv2.imencode('.png', image)
    return base64.b64encode(buffer).decode()


def make_message(image_base64: str, prompt: str) -> list:
    return [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            {"type": "text", "text": prompt}
        ]
    }]


def ensure_model_init():
    """阻塞式检测可用 VL 模型（仅首次调用时执行，线程安全）"""
    global current_model_type, model_init_done
    if model_init_done:
        return
    with model_init_lock:
        if model_init_done:
            return
        preferred = read_vl_config().get("type", "vllm").lower()

        # 并行探测所有模型
        probe_results = probe_all_services()

        # 优先使用配置的首选类型
        if probe_results.get(preferred):
            current_model_type = preferred
            model_init_done = True
            return

        print(f"{preferred} 不可用，回退到其他模型")

        # 按优先级回退
        for mt in PROVIDERS:
            if probe_results.get(mt):
                current_model_type = mt
                print(f"自动切换到 {PROVIDERS[mt].display} ({PROVIDERS[mt].model_name})")
                break
        model_init_done = True


def clean_vlm_response(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    for token in ['<|observation|>', '<|user|>', '<|assistant|>', '<|endoftext|>']:
        text = text.replace(token, '')
    text = ' '.join(text.split())
    return text.strip()


def call_vlm_func(image: np.ndarray, prompt: str, max_tokens: int = 64, temperature: float = 0.1,
              model_type: str = None) -> Optional[str]:
    """统一的 VLM 调用入口，根据 model_type 路由到对应提供者"""
    if image is None or image.size == 0:
        return None

    ensure_model_init()
    provider_key = model_type or current_model_type
    provider = get_provider(provider_key)
    client = get_client_ref(provider_key)
    image_base64 = image_to_base64(image)
    msg = make_message(image_base64, prompt)

    # SiliconFlow 有并发限制，走重试+信号量逻辑；其他模型直接调用
    if provider_key == MODEL_TYPE_SILICONFLOW:
        return call_vlm_with_retry(client, provider, msg, max_tokens, temperature)

    try:
        response = client.chat.completions.create(
            model=provider.model_name,
            messages=msg,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw = response.choices[0].message.content
        return clean_vlm_response(raw)
    except Exception as e:
        print(f"VLM API error ({provider.display}): {e}")
        return None


def call_vlm_with_retry(client: OpenAI, provider: ModelProvider, msg: list,
                         max_tokens: int, temperature: float) -> Optional[str]:
    """带重试和并发控制的 VLM 调用（用于 SiliconFlow 等有速率限制的服务）"""
    for attempt in range(provider.max_retries):
        with siliconflow_semaphore:
            try:
                response = client.chat.completions.create(
                    model=provider.model_name,
                    messages=msg,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                raw = response.choices[0].message.content
                return clean_vlm_response(raw)
            except Exception as e:
                err_str = str(e)
                is_rate_limit = '429' in err_str
                if not is_rate_limit or attempt >= provider.max_retries - 1:
                    print(f"VLM API error ({provider.display}): {e}")
                    return None
        time.sleep(2 ** attempt)
    return None


# ==================== OCR 单项识别 ====================

def ocr_digits(roi_image: np.ndarray) -> Optional[int]:
    result = call_vlm_func(roi_image, "识别图片中的数字，只输出数字本身，不要输出其他任何内容。数字可能包含斜杠（如 26/31）。")
    if result:
        text = result.replace(' ', '').strip().rstrip(".")
        if '/' in text:
            text = text.split('/')[1]
        return int(text)
    return None


def ocr_nature(roi_image: np.ndarray) -> Optional[str]:
    nature_list = "\n".join([f"- {n}" for n in NATURES])
    prompt = f"识别图片中的宝可梦性格（Nature）。\n性格只能是以下25种之一：\n{nature_list}\n只输出性格名称，首字母大写，不要输出其他任何内容。"
    result = call_vlm_func(roi_image, prompt)
    if result:
        return result.strip().upper()
    return None


def ocr_ability(roi_image: np.ndarray) -> Optional[str]:
    prompt = "识别图片中的宝可梦特性（Ability）名称。只输出特性名称，全部大写，保留单词之间的空格，不要输出其他任何内容。"
    result = call_vlm_func(roi_image, prompt)
    if result:
        return result.strip().upper()
    return None


# ==================== 高级 OCR 接口 (直接基于 1920×1080 ROI) ====================

def crop_roi(image, roi):
    x, y, w, h = roi
    return image[y:y+h, x:x+w]


def parallel_ocr(tasks: List[Tuple[str, np.ndarray, callable]]) -> Dict[str, object]:
    """
    并行执行多个 OCR 任务。

    tasks: [(key, roi_image, ocr_function), ...]
    返回的 dict 按 task 定义顺序排列 key。
    """
    provider = get_provider(current_model_type)
    max_workers = min(provider.max_concurrency, len(tasks))
    raw: Dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(ocr_func, img): key for key, img, ocr_func in tasks}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                val = fut.result()
                raw[key] = val if val is not None else ""
            except Exception:
                raw[key] = ""
    # 按 task 定义顺序重建 dict，消除多线程乱序
    results: Dict[str, object] = {}
    for key, _, _ in tasks:
        if key in raw:
            results[key] = raw[key]
    return results


def ocr_elevated(image: np.ndarray) -> Dict[str, object]:
    """
    Elevated (查看IV) 界面 OCR。并行调用 VL 模型。

    输入 1920×1080 BGR 图像，返回平铺字典:
        {'level': '50', 'hp': '31', 'attack': '15', 'defense': '20',
         'sp_atk': '25', 'sp_def': '30', 'speed': '31'}
    """
    tasks = [
        ('level', crop_roi(image, ELEVATED_LEVEL_RECT), ocr_digits),
        ('hp', crop_roi(image, ELEVATED_STAT_RECTS[0]), ocr_digits),
        ('attack', crop_roi(image, ELEVATED_STAT_RECTS[1]), ocr_digits),
        ('defense', crop_roi(image, ELEVATED_STAT_RECTS[2]), ocr_digits),
        ('sp_atk', crop_roi(image, ELEVATED_STAT_RECTS[3]), ocr_digits),
        ('sp_def', crop_roi(image, ELEVATED_STAT_RECTS[4]), ocr_digits),
        ('speed', crop_roi(image, ELEVATED_STAT_RECTS[5]), ocr_digits),
    ]
    return parallel_ocr(tasks)


def ocr_caught_info(image: np.ndarray) -> Dict[str, object]:
    """
    Caught Info 界面 OCR (等级、性别、性格)。并行调用 VL 模型。

    输入 1920×1080 BGR 图像，返回平铺字典:
        {'level': '50', 'gender': 'male', 'nature': 'ADAMANT'}
    """
    tasks = [
        ('level', crop_roi(image, CAUGHT_LEVEL_RECT), ocr_digits),
        ('nature', crop_roi(image, CAUGHT_NATURE_RECT), ocr_nature),
    ]
    return parallel_ocr(tasks)


def ocr_caught_iv(image: np.ndarray) -> Dict[str, object]:
    """
    Caught IV 界面 OCR (等级、特性、6项能力值)。并行调用 VL 模型。

    输入 1920×1080 BGR 图像，返回平铺字典:
        {'level': '50', 'ability': 'TORRENT',
         'hp': '31', 'attack': '15', 'defense': '20',
         'sp_atk': '25', 'sp_def': '30', 'speed': '31'}
    """
    tasks = [
        ('level', crop_roi(image, CAUGHT_LEVEL_RECT), ocr_digits),
        ('hp', crop_roi(image, CAUGHT_STAT_HP_RECT), ocr_digits),
        ('attack', crop_roi(image, CAUGHT_STAT_OTHER_RECTS[0]), ocr_digits),
        ('defense', crop_roi(image, CAUGHT_STAT_OTHER_RECTS[1]), ocr_digits),
        ('sp_atk', crop_roi(image, CAUGHT_STAT_OTHER_RECTS[2]), ocr_digits),
        ('sp_def', crop_roi(image, CAUGHT_STAT_OTHER_RECTS[3]), ocr_digits),
        ('speed', crop_roi(image, CAUGHT_STAT_OTHER_RECTS[4]), ocr_digits),
        ('ability', crop_roi(image, CAUGHT_ABILITY_RECT), ocr_ability),
    ]
    return parallel_ocr(tasks)


def ocr_pokemon(image: Optional[np.ndarray] = None) -> Dict[str, object]:
    """
    自动检测画面类型并 OCR。一键入口。

    返回带有 'screen' 键的平铺字典，例如:
        {'screen': 'ELEVATED', 'level': '50', 'hp': '31', ...}
    检测失败返回 {'screen': 'UNKNOWN'}。
    """
    if image is None:
        return {'screen': SCREEN_UNKNOWN}
    if image.shape[:2] != (SRC_HEIGHT, SRC_WIDTH):
        full = cv2.resize(image, (SRC_WIDTH, SRC_HEIGHT), interpolation=cv2.INTER_LANCZOS4)
    else:
        full = image
    screen_type = classify_screen_type(full, debug=False)
    if screen_type == SCREEN_ELEVATED:
        result = ocr_elevated(image)
    elif screen_type == SCREEN_CAUGHT_INFO:
        result = ocr_caught_info(image)
    elif screen_type == SCREEN_CAUGHT_IV:
        result = ocr_caught_iv(image)
    else:
        return {'screen': SCREEN_UNKNOWN}
    result['screen'] = screen_type
    return result


def ocr_custom(roi_image: np.ndarray, prompt: str, model_type: str = None) -> Optional[str]:
    return call_vlm_func(roi_image, prompt, max_tokens=128, temperature=0.2, model_type=model_type)


# 拾取道具提示 ROI：来自 labels/roi-miaomiao.IL 的 Target 区域
TAKEN_ITEM_ROI = (208, 774, 1485, 228)


def ocr_taken_item(frame: np.ndarray) -> Optional[str]:
    x, y, w, h = TAKEN_ITEM_ROI
    h_frame, w_frame = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w_frame, x + w), min(h_frame, y + h)
    roi = frame[y1:y2, x1:x2]
    prompt = "识别图片中的文字，只输出文字内容本身，不要添加任何额外描述或格式。"
    result = call_vlm_func(roi, prompt, max_tokens=128, temperature=0.1)
    return result.strip() if result else None


# 宝可梦名字识别 ROI：来自 labels/roi.IL 的 Target 区域
NAME_ROI = (300, 135, 400, 55)


def ocr_pokemon_name(frame: np.ndarray, candidates: list, debug: bool = True) -> Optional[str]:
    """
    识别野生宝可梦英文名，识别野生血条上方、等级左侧区域

    candidates: 备选列表，如 ["走路草(Oddish)", "嘟嘟(Doduo)"]
    返回英文名或 None。debug=True 时保存标注图和裁剪图到 debug_label/。
    """
    import cv2, time as _time, os as _os

    NX, NY, NW, NH = NAME_ROI
    h, w = frame.shape[:2]
    x1, y1 = max(0, NX), max(0, NY)
    x2, y2 = min(w, NX + NW), min(h, NY + NH)
    roi = frame[y1:y2, x1:x2]

    if debug:
        try:
            _os.makedirs('debug_label', exist_ok=True)
            ts = _time.strftime('%Y%m%d_%H%M%S')
            dbg = frame.copy()
            cv2.rectangle(dbg, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.imwrite(f'debug_label/name_roi_{ts}.png', dbg)
            cv2.imwrite(f'debug_label/name_roi_{ts}_crop.png', roi)
        except Exception:
            pass

    if not candidates:
        return None

    prompt = (
        "Which Pokemon is in this image? Choose from: "
        + ", ".join(candidates)
        + ". Reply with ONLY the English name, or NONE if none match."
    )
    result = call_vlm_func(roi, prompt, max_tokens=128, temperature=0.2)
    return result.strip() if result else None
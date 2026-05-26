"""
Pokemon OCR Module - 宝可梦信息 OCR 识别模块
通过 WSL vLLM 部署的 Qwen3-VL-2B 进行图像识别，提供给 EasyCon 脚本使用

ROI 坐标基于 1920×1080 (采集卡直出)

配置来源：config/default.yaml → vl_model 段
"""

import base64
from fnmatch import translate
import os
import time
import threading
from typing import Optional, Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

# ==================== VL 模型配置（config/default.yaml → vl_model 段） ====================

def _read_vl_config():
    """读取 VL 模型配置（延迟导入，避免循环依赖）"""
    try:
        from easycon.config import get
        return get("vl_model", {})
    except Exception:
        return {}

_vl_cfg = _read_vl_config()

VLLM_BASE_URL = _vl_cfg.get("vllm", {}).get("base_url", "http://localhost:8000/v1")
VLLM_API_KEY = _vl_cfg.get("vllm", {}).get("api_key", "sk-PyEasyCon")
VLLM_MODEL_NAME = _vl_cfg.get("vllm", {}).get("model_name", "/opt/models/Qwen3-VL-2B-Instruct-FP8")

GLM_API_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_API_KEY = _vl_cfg.get("glm", {}).get("api_key", "")
GLM_MODEL = _vl_cfg.get("glm", {}).get("model", "glm-4.6v-flash")
GLM_MAX_RETRIES = _vl_cfg.get("glm", {}).get("max_retries", 8)

MODEL_TYPE_VLLM = "vllm"
MODEL_TYPE_GLM = "glm"

_preferred = _vl_cfg.get("type", "vllm").lower()
_current_model_type = (
    MODEL_TYPE_GLM if _preferred == "glm"
    else MODEL_TYPE_VLLM if _preferred == "vllm"
    else MODEL_TYPE_VLLM
)

_model_init_done = False
_model_init_lock = threading.Lock()

_glm_semaphore = threading.Semaphore(2)

_client = None
_glm_client = None
_openai_available = False

try:
    from openai import OpenAI
    _openai_available = True
except ImportError:
    pass

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


# ==================== VL 客户端 & 服务检测 ====================

def _make_message(image_base64: str, prompt: str) -> list:
    return [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            {"type": "text", "text": prompt}
        ]
    }]


def _probe_openai(base_url: str, api_key: str, timeout: float = 5) -> bool:
    if not _openai_available:
        return False
    try:
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        models = client.models.list()
        return len(models.data) > 0
    except Exception:
        return False


def _get_vllm_client() -> OpenAI:
    global _client
    if not _openai_available:
        raise ImportError("openai 库未安装，请运行: pip install openai")
    if _client is None:
        _client = OpenAI(api_key=VLLM_API_KEY, base_url=VLLM_BASE_URL, timeout=60)
    return _client


def _get_glm_client() -> OpenAI:
    global _glm_client
    if not _openai_available:
        raise ImportError("openai 库未安装，请运行: pip install openai")
    if _glm_client is None:
        _glm_client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_API_BASE_URL, timeout=60)
    return _glm_client


def set_model_type(model_type: str):
    global _current_model_type
    if model_type not in [MODEL_TYPE_VLLM, MODEL_TYPE_GLM]:
        raise ValueError(f"不支持的模型类型: {model_type}，支持的类型: {MODEL_TYPE_VLLM}, {MODEL_TYPE_GLM}")
    _current_model_type = model_type


def get_current_model_type() -> str:
    return _current_model_type


def get_available_model_types() -> list:
    available = []
    if _probe_openai(VLLM_BASE_URL, VLLM_API_KEY):
        available.append(MODEL_TYPE_VLLM)
    if _probe_openai(GLM_API_BASE_URL, GLM_API_KEY):
        available.append(MODEL_TYPE_GLM)
    return available


def get_vllm_model() -> str:
    if not _probe_openai(VLLM_BASE_URL, VLLM_API_KEY):
        raise RuntimeError("vLLM 服务不可用")
    return VLLM_MODEL_NAME


def check_service() -> bool:
    if _current_model_type == MODEL_TYPE_VLLM:
        return _probe_openai(VLLM_BASE_URL, VLLM_API_KEY)
    elif _current_model_type == MODEL_TYPE_GLM:
        return _probe_openai(GLM_API_BASE_URL, GLM_API_KEY)
    return False


def check_vllm_service() -> bool:
    return _probe_openai(VLLM_BASE_URL, VLLM_API_KEY)


def check_glm_service() -> bool:
    return _probe_openai(GLM_API_BASE_URL, GLM_API_KEY)


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


# ==================== vLLM OCR 调用 ====================

def _image_to_base64(image: np.ndarray) -> str:
    _, buffer = cv2.imencode('.png', image)
    return base64.b64encode(buffer).decode()


def _ensure_model_init():
    """阻塞式检测可用 VL 模型（仅首次调用时执行，线程安全）"""
    global _current_model_type, _model_init_done
    if _model_init_done:
        return
    with _model_init_lock:
        if _model_init_done:
            return
        preferred = _read_vl_config().get("type", "vllm").lower()

        if preferred == "glm":
            if check_glm_service():
                _current_model_type = MODEL_TYPE_GLM
                _model_init_done = True
                return
            print("GLM 不可用，回退到 vLLM")

        vllm_ok = check_vllm_service()
        glm_ok = check_glm_service()
        if vllm_ok:
            _current_model_type = MODEL_TYPE_VLLM
        elif glm_ok:
            _current_model_type = MODEL_TYPE_GLM
            print(f"vLLM 未运行，自动切换到 {GLM_MODEL} 在线API")
        _model_init_done = True


def _clean_vlm_response(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    for token in ['<|observation|>', '<|user|>', '<|assistant|>', '<|endoftext|>']:
        text = text.replace(token, '')
    text = ' '.join(text.split())
    return text.strip()


def _call_vlm(image: np.ndarray, prompt: str, max_tokens: int = 64, temperature: float = 0.1,
              model_type: str = None) -> Optional[str]:
    if image is None or image.size == 0:
        return None

    _ensure_model_init()
    effective_model = model_type or _current_model_type
    image_base64 = _image_to_base64(image)
    msg = _make_message(image_base64, prompt)

    try:
        if effective_model == MODEL_TYPE_VLLM:
            response = _get_vllm_client().chat.completions.create(
                model=VLLM_MODEL_NAME,
                messages=msg,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            raw = response.choices[0].message.content
            return _clean_vlm_response(raw)

        elif effective_model == MODEL_TYPE_GLM:
            for attempt in range(GLM_MAX_RETRIES):
                with _glm_semaphore:
                    try:
                        response = _get_glm_client().chat.completions.create(
                            model=GLM_MODEL,
                            messages=msg,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            extra_body={"thinking": {"type": "disabled"}},
                        )
                        raw = response.choices[0].message.content
                        return _clean_vlm_response(raw)
                    except Exception as e:
                        err_str = str(e)
                        is_rate_limit = '429' in err_str or '1302' in err_str or '1305' in err_str
                        if not is_rate_limit or attempt >= GLM_MAX_RETRIES - 1:
                            raise
                wait = 2 ** attempt
                print(f"GLM rate limit, retry in {wait:.0f}s (attempt {attempt + 1}/{GLM_MAX_RETRIES})")
                time.sleep(wait)

        else:
            raise ValueError(f"不支持的模型类型: {effective_model}")

    except Exception as e:
        print(f"VLM API error: {e}")
        return None


# ==================== OCR 单项识别 ====================

def ocr_digits(roi_image: np.ndarray) -> Optional[int]:
    result = _call_vlm(roi_image, "识别图片中的数字，只输出数字本身，不要输出其他任何内容。数字可能包含斜杠（如 26/31）。")
    if result:
        text = result.replace(' ', '').strip().rstrip(".")
        if '/' in text:
            text = text.split('/')[1]
        return int(text)
    return None


def ocr_nature(roi_image: np.ndarray) -> Optional[str]:
    nature_list = "\n".join([f"- {n}" for n in NATURES])
    prompt = f"识别图片中的宝可梦性格（Nature）。\n性格只能是以下25种之一：\n{nature_list}\n只输出性格名称，首字母大写，不要输出其他任何内容。"
    result = _call_vlm(roi_image, prompt)
    if result:
        return result.strip().upper()
    return None


def ocr_ability(roi_image: np.ndarray) -> Optional[str]:
    prompt = "识别图片中的宝可梦特性（Ability）名称。只输出特性名称，全部大写，保留单词之间的空格，不要输出其他任何内容。"
    result = _call_vlm(roi_image, prompt)
    if result:
        return result.strip().upper()
    return None





# ==================== 高级 OCR 接口 (直接基于 1920×1080 ROI) ====================

def _crop_roi(image, roi):
    x, y, w, h = roi
    return image[y:y+h, x:x+w]


def _parallel_ocr(tasks: List[Tuple[str, np.ndarray, callable]]) -> Dict[str, object]:
    """
    并行执行多个 OCR 任务。

    tasks: [(key, roi_image, ocr_function), ...]
    """
    max_workers = 4 if _current_model_type == MODEL_TYPE_GLM else min(len(tasks), 8)
    results: Dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(ocr_func, img): key for key, img, ocr_func in tasks}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                val = fut.result()
                results[key] = val if val is not None else ""
            except Exception:
                results[key] = ""
    return results


def ocr_elevated(image: np.ndarray) -> Dict[str, object]:
    """
    Elevated (查看IV) 界面 OCR。并行调用 vLLM。

    输入 1920×1080 BGR 图像，返回平铺字典:
        {'level': '50', 'hp': '31', 'attack': '15', 'defense': '20',
         'sp_atk': '25', 'sp_def': '30', 'speed': '31'}
    """
    tasks = [('level', _crop_roi(image, ELEVATED_LEVEL_RECT), ocr_digits)]
    stat_names = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed']
    for name, roi in zip(stat_names, ELEVATED_STAT_RECTS):
        tasks.append((name, _crop_roi(image, roi), ocr_digits))
    return _parallel_ocr(tasks)


def ocr_caught_info(image: np.ndarray) -> Dict[str, object]:
    """
    Caught Info 界面 OCR (等级、性别、性格)。并行调用 vLLM。

    输入 1920×1080 BGR 图像，返回平铺字典:
        {'level': '50', 'gender': 'male', 'nature': 'ADAMANT'}
    """
    tasks = [
        ('level', _crop_roi(image, CAUGHT_LEVEL_RECT), ocr_digits),
        ('nature', _crop_roi(image, CAUGHT_NATURE_RECT), ocr_nature),
    ]
    return _parallel_ocr(tasks)


def ocr_caught_iv(image: np.ndarray) -> Dict[str, object]:
    """
    Caught IV 界面 OCR (等级、特性、6项能力值)。并行调用 vLLM。

    输入 1920×1080 BGR 图像，返回平铺字典:
        {'level': '50', 'ability': 'TORRENT',
         'hp': '31', 'attack': '15', 'defense': '20',
         'sp_atk': '25', 'sp_def': '30', 'speed': '31'}
    """
    stat_names = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed']
    tasks = [
        ('level', _crop_roi(image, CAUGHT_LEVEL_RECT), ocr_digits),
        ('ability', _crop_roi(image, CAUGHT_ABILITY_RECT), ocr_ability),
    ]
    iv_rois = [CAUGHT_STAT_HP_RECT] + CAUGHT_STAT_OTHER_RECTS
    for name, roi in zip(stat_names, iv_rois):
        tasks.append((name, _crop_roi(image, roi), ocr_digits))
    return _parallel_ocr(tasks)


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
    return _call_vlm(roi_image, prompt, max_tokens=128, temperature=0.2, model_type=model_type)


# 拾取道具提示 ROI：来自 labels/roi-miaomiao.IL 的 Target 区域
_TAKEN_ITEM_ROI = (208, 774, 1485, 228)


def ocr_taken_item(frame: np.ndarray) -> Optional[str]:
    x, y, w, h = _TAKEN_ITEM_ROI
    h_frame, w_frame = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w_frame, x + w), min(h_frame, y + h)
    roi = frame[y1:y2, x1:x2]
    prompt = "识别图片中的文字，只输出文字内容本身，不要添加任何额外描述或格式。"
    result = _call_vlm(roi, prompt, max_tokens=128, temperature=0.1)
    return result.strip() if result else None


# 宝可梦名字识别 ROI：来自 labels/roi.IL 的 Target 区域
_NAME_ROI = (300, 135, 400, 55)


def ocr_pokemon_name(frame: np.ndarray, candidates: list, debug: bool = True) -> Optional[str]:
    """
    识别野生宝可梦英文名，识别野生血条上方、等级左侧区域
    
    candidates: 备选列表，如 ["走路草(Oddish)", "嘟嘟(Doduo)"]
    返回英文名或 None。debug=True 时保存标注图和裁剪图到 debug_label/。
    """
    import cv2, time as _time, os as _os

    NX, NY, NW, NH = _NAME_ROI
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
    result = _call_vlm(roi, prompt, max_tokens=128, temperature=0.2)
    return result.strip() if result else None
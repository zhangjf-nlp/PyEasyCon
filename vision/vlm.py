"""
VLM 统一调用模块 - OpenAI 兼容 API 的 VL 模型基础设施

配置来源：default.yaml → vl_model 段
"""

import base64
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor

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


# ==================== VL 客户端 & 服务检测（统一层） ====================

def get_client_ref(provider_key: str) -> "OpenAI":
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


# ==================== VLM 调用 ====================

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


def call_vlm_with_retry(client: "OpenAI", provider: ModelProvider, msg: list,
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

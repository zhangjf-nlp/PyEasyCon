import os
import yaml
from typing import Any, Dict


config_data: Dict[str, Any] = {}
loaded_flag = False


def load_config(config_path: str = None) -> Dict[str, Any]:
    global config_data, loaded_flag

    if loaded_flag:
        return config_data

    if config_path is None:
        config_path = os.environ.get(
            "EASYCON_CONFIG",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "default.yaml"),
        )

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
    else:
        config_data = {}

    loaded_flag = True
    return config_data


def get_config() -> Dict[str, Any]:
    if not loaded_flag:
        load_config()
    return config_data


def get(key: str, default: Any = None) -> Any:
    cfg = get_config()
    keys = key.split(".")
    val = cfg
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
        if val is None:
            return default
    return val


def reload_config(config_path: str = None):
    global config_data, loaded_flag
    config_data = {}
    loaded_flag = False
    return load_config(config_path)
import os
import yaml
from typing import Any, Dict


_config: Dict[str, Any] = {}
_loaded = False


def load_config(config_path: str = None) -> Dict[str, Any]:
    global _config, _loaded

    if _loaded:
        return _config

    if config_path is None:
        config_path = os.environ.get(
            "EASYCON_CONFIG",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "default.yaml"),
        )

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
    else:
        _config = {}

    _loaded = True
    return _config


def get_config() -> Dict[str, Any]:
    if not _loaded:
        load_config()
    return _config


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
    global _config, _loaded
    _config = {}
    _loaded = False
    return load_config(config_path)
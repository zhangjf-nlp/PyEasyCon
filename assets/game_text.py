"""
游戏公共文本数据 — 从 assets/game_text.json 加载。
统一管理宝可梦中英文译名、地点、分类等公共映射。
"""
import json
import os


def load_game_text():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "game_text.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


game_text = load_game_text()

# ── 宝可梦译名 ──
SPECIES_EN_TO_ZH: dict = game_text["species_en_to_zh"]
SPECIES_ZH_TO_EN: dict = {v: k for k, v in SPECIES_EN_TO_ZH.items()}

# 向后兼容别名
STATIC_POKEMON_EN_TO_ZH = SPECIES_EN_TO_ZH
STATIC_POKEMON_ZH_TO_EN = SPECIES_ZH_TO_EN

# ── 遇敌分类 ──
CATEGORY_ZH_TO_EN: dict = game_text["category_zh_to_en"]
CATEGORY_EN_TO_ZH: dict = {v: k for k, v in CATEGORY_ZH_TO_EN.items()}

# ── 遇敌方式 ──
METHOD_ZH_TO_EN: dict = game_text["method_zh_to_en"]
METHOD_EN_TO_ZH: dict = {v: k for k, v in METHOD_ZH_TO_EN.items()}

STATIC_CATEGORIES: list = game_text["static_categories"]
WILD_CATEGORIES: list = game_text["wild_categories"]

# ── 静态宝可梦分组 ──
STATIC_POKEMON_MAP: dict = game_text["static_pokemon_map"]

# ── 地点 ──
LOCATION_EN_TO_ZH: dict = game_text["location_en_to_zh"]
LOCATION_ZH_TO_EN: dict = {v: k for k, v in LOCATION_EN_TO_ZH.items()}

# ── 游戏设置 ──
SOUND_ZH_TO_EN: dict = game_text["sound_zh_to_en"]
SOUND_EN_TO_ZH: dict = {v: k for k, v in SOUND_ZH_TO_EN.items()}

BTN_MODE_ZH_TO_EN: dict = game_text["btn_mode_zh_to_en"]
BTN_MODE_EN_TO_ZH: dict = {v: k for k, v in BTN_MODE_ZH_TO_EN.items()}

SEED_BTN_ZH_TO_EN: dict = game_text["seed_btn_zh_to_en"]
SEED_BTN_EN_TO_ZH: dict = {v: k for k, v in SEED_BTN_ZH_TO_EN.items()}

EXTRA_BTN_ZH_TO_EN: dict = game_text["extra_btn_zh_to_en"]
EXTRA_BTN_EN_TO_ZH: dict = {v: k for k, v in EXTRA_BTN_ZH_TO_EN.items()}


# ── 努力值属性 ──
STAT_ZH_MAP: dict = game_text["stat_zh_map"]
ALL_STATS: list = game_text["all_stats"]


# ── 辅助函数 ──

def location_to_zh(en_name: str) -> str:
    """英文地点名 → 中文"""
    return LOCATION_EN_TO_ZH.get(en_name, en_name)


def location_to_en(zh_name: str) -> str:
    """中文地点名 → 英文"""
    return LOCATION_ZH_TO_EN.get(zh_name, zh_name)


def species_to_zh(en_name: str) -> str:
    """英文宝可梦名 → 中文"""
    return SPECIES_EN_TO_ZH.get(en_name, en_name)


def species_to_en(zh_name: str) -> str:
    """中文宝可梦名 → 英文"""
    return SPECIES_ZH_TO_EN.get(zh_name, zh_name)
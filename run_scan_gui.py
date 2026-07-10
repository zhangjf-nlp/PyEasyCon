# -*- coding: utf-8 -*-
import os
import subprocess
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launch_gui import (
    LaunchGUI,
    get_font, C_TEXT_DIM,
    C_RED,
    ROW_H, ROW_GAP, SIDE_PAD,
)
from rng.tenlines_utils import (
    get_encounter_species_list,
    get_species_id,
    get_species_name,
    load_frlg_encounters,
)
from assets.game_text import (
    STATIC_CATEGORIES, WILD_CATEGORIES, STATIC_POKEMON_MAP,
    SPECIES_EN_TO_ZH, SPECIES_ZH_TO_EN,
    METHOD_ZH_TO_EN, METHOD_EN_TO_ZH,
    CATEGORY_ZH_TO_EN, CATEGORY_EN_TO_ZH,
    location_to_zh as loc_zh, location_to_en as loc_en,
)
from easycon.config import get
from easycon.controller import EasyConController
from script_utils.hit import EXTRA_A_PRESSES

# ── constants ──────────────────────────────────────────────────────────────────
GAME_OPTIONS = {"火红": "fr_nx", "叶绿": "lg_nx"}

METHOD_OPTIONS = {
    "Static": {"categories": STATIC_CATEGORIES},
    "Wild":   {"categories": WILD_CATEGORIES},
}

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "scan_logs", "latest.json")


def get_all_locations() -> dict:
    cat_to_locs: dict = {}
    for gv in ("fr_nx", "lg_nx"):
        for (loc, cat) in load_frlg_encounters(gv).keys():
            cat_to_locs.setdefault(cat, set()).add(loc)
    return {cat: sorted(locs) for cat, locs in cat_to_locs.items()}

# ── ScanGui ────────────────────────────────────────────────────────────────────

class ScanGui(LaunchGUI):
    TOTAL_SCALE = 2
    WINDOW_TITLE = "EasyCon Scan 配置"

    def __init__(self):
        self.all_locations = get_all_locations()
        super().__init__()
        self.panel_bg = True
        self.show_instructions()

    def show_instructions(self):
        """显示前置说明"""
        title = "穷举遍历刷闪 - 使用说明"
        msg = (
            "【功能说明】\n"
            "不断遭遇宝可梦刷闪\n"
            "无需获知TID/SID\n"
            "支持：草丛/钓鱼/冲浪/定点/礼物\n"
            "不支持：游走/御三家/部分定点\n"
            "\n"
            "【前置准备】\n"
            "0. 游戏：【NS/NS2】&【英文版FRLG】\n"
            "1. 硬件：【单片机】&【采集卡】\n"
            "2. 游戏存档：\n"
            "    【定点】面对宝可梦/礼物/NPC保存\n"
            "    【狩猎区】使用完黄金喷雾&站在收费口精灵球图标上保存\n"
            "    【草丛】站草丛保存【冲浪】冲浪中保存【钓鱼】面对水面保存\n"
            "3. NS回到主页&切换用户&选择好用户 -> 【准备完毕】"
        )
        self.show_message(title, msg)

    def cache_file(self) -> str:
        return CACHE_FILE

    # ── cache ──────────────────────────────────────────────────────────────────

    def apply_cache(self, data):
        game = data.get("game", "")
        if game in self.game_combo.all_options:
            self.game_combo.selected_index = self.game_combo.all_options.index(game)

        method_en   = data.get("method", "")
        method_disp = METHOD_EN_TO_ZH.get(method_en, method_en)
        if method_disp in self.method_combo.all_options:
            self.method_combo.selected_index = self.method_combo.all_options.index(method_disp)
        self.method_combo.filter_text_ = ""
        self.method_combo.apply_filter()

        cats_en   = METHOD_OPTIONS.get(method_en, {}).get("categories", [])
        cats_disp = [CATEGORY_EN_TO_ZH.get(c, c) for c in cats_en]
        self.category_combo.set_options(cats_disp)
        cat_disp = CATEGORY_EN_TO_ZH.get(data.get("category", ""), "")
        if cat_disp in self.category_combo.all_options:
            self.category_combo.selected_index = self.category_combo.all_options.index(cat_disp)
        self.category_combo.filter_text_ = ""
        self.category_combo.apply_filter()

        self.reload_location_options(method_en, data.get("category", ""))
        loc_disp = loc_zh(data.get("location", ""))
        if loc_disp in self.location_combo.all_options:
            self.location_combo.selected_index = self.location_combo.all_options.index(loc_disp)
        self.location_combo.filter_text_ = ""
        self.location_combo.apply_filter()

        self.refresh_pokemon_options()
        pkm_zh = SPECIES_EN_TO_ZH.get(data.get("pokemon", ""), data.get("pokemon", ""))
        if pkm_zh and pkm_zh in self.pokemon_combo.all_options:
            self.pokemon_combo.selected_index = self.pokemon_combo.all_options.index(pkm_zh)
            self.pokemon_combo.filter_text_ = ""
            self.pokemon_combo.apply_filter()

    def save_cache(self, data):
        self.save_cache_impl(data)

    # ── layout ─────────────────────────────────────────────────────────────────

    def build_ui(self):
        y = SIDE_PAD

        # row 1: Method(1) | Category(1)
        method_opts = [METHOD_EN_TO_ZH.get(m, m) for m in METHOD_OPTIONS]
        method_cb   = self.make_combobox(0, 0, 0, ROW_H, method_opts, "野生", on_change=self.on_method_change)
        self.method_combo = method_cb

        cat_cb = self.make_combobox(0, 0, 0, ROW_H, [], "草丛", on_change=self.on_category_change)
        self.category_combo = cat_cb

        y = self.add_row(y, [
            (1, "方法:",   method_cb, {}),
            (1, "分类:",   cat_cb,   {}),
        ])

        # row 2: Location(2)
        loc_cb = self.make_combobox(0, 0, 0, ROW_H, [], "刷闪地点",
                                    on_change=self.on_location_change)
        self.location_combo = loc_cb
        y = self.add_row(y, [(2, "地点:", loc_cb, {})])

        # row 3: Game(1) | Pokemon(1)
        game_cb = self.make_combobox(0, 0, 0, ROW_H, list(GAME_OPTIONS.keys()), "火红")
        game_cb.selected_index = 0
        self.game_combo = game_cb

        pkm_cb = self.make_combobox(0, 0, 0, ROW_H, [], "刷闪宝可梦")
        self.pokemon_combo = pkm_cb
        y = self.add_row(y, [
            (1, "Game:",  game_cb, {}),
            (1, "宝可梦:", pkm_cb, {}),
        ])

        # button row
        y = self.add_button_row(y, [
            ("确定", self.on_confirm),
            ("重置", self.on_reset),
            ("退出", self.on_quit),
        ], right_callbacks={0: lambda: self.on_confirm(skip_checks=True)})

        self.H = self.final_height(y)
        self.resize_to_fit()

        self.status_text  = ""
        self.status_color = C_TEXT_DIM
        self.status_font  = get_font(13)

    # ── cascade ────────────────────────────────────────────────────────────────

    def get_method_en(self):
        return METHOD_ZH_TO_EN.get(self.method_combo.get_value(), self.method_combo.get_value())

    def get_category_en(self):
        return CATEGORY_ZH_TO_EN.get(self.category_combo.get_value(), self.category_combo.get_value())

    def get_location_en(self):
        return loc_en(self.location_combo.get_value())

    def reload_location_options(self, method_en, cat_en):
        if method_en == "Wild" and cat_en:
            locs = [loc_zh(l) for l in self.all_locations.get(cat_en, [])]
            self.location_combo.set_options(locs, 0 if locs else -1)
        elif method_en == "Static" and cat_en:
            self.location_combo.set_options([CATEGORY_EN_TO_ZH.get(cat_en, cat_en)], 0)
        else:
            self.location_combo.set_options([])

    def refresh_pokemon_options(self):
        method_en = self.get_method_en()
        cat_en    = self.get_category_en()
        loc_en_val = self.get_location_en()
        game_ver  = GAME_OPTIONS.get(self.game_combo.get_value(), "fr_nx")
        if method_en == "Static" and cat_en:
            pkms = [SPECIES_EN_TO_ZH.get(p, p) for p in STATIC_POKEMON_MAP.get(cat_en, [])]
        elif method_en == "Wild" and loc_en_val and cat_en:
            ids  = get_encounter_species_list(loc_en_val, cat_en, game_ver)
            pkms = [SPECIES_EN_TO_ZH.get(get_species_name(s), str(s)) for s in ids]
        else:
            pkms = []
        self.pokemon_combo.set_options(pkms, 0 if pkms else -1)

    def on_method_change(self):
        method_en = self.get_method_en()
        cats_en   = METHOD_OPTIONS.get(method_en, {}).get("categories", [])
        self.category_combo.set_options(
            [CATEGORY_EN_TO_ZH.get(c, c) for c in cats_en], 0 if cats_en else -1)
        self.on_category_change()

    def on_category_change(self):
        self.reload_location_options(self.get_method_en(), self.get_category_en())
        self.refresh_pokemon_options()

    def on_location_change(self):
        self.refresh_pokemon_options()

    # ── buttons ────────────────────────────────────────────────────────────────

    def set_status(self, text, color):
        self.status_text  = text
        self.status_color = color

    def on_confirm(self, skip_checks: bool = False):
        data = self.collect_inputs()
        if data is None:
            self.set_status("请填写所有必填字段。", C_RED)
            return

        # ── 参数校验 ──
        errs = self.validate(data)
        if errs:
            self.show_message("配置校验失败", "\n\n".join(errs))
            self.set_status(errs[0], C_RED)
            return

        if skip_checks:
            # 右键跳过：仅做参数校验，不检测硬件
            self.save_cache(data)
            self.result = data
            self.running = False
            return

        # ── 硬件检测 ──
        progress = {"step": 0, "failed_msg": ""}

        def checks():
            progress["step"] = 1
            try:
                c = EasyConController()
                if not c.list_ports() or not c.connect(timeout=2.0):
                    progress["failed_msg"] = "未识别到可用控制器"
                    return
                c.disconnect()
            except Exception:
                progress["failed_msg"] = "未识别到可用控制器"
                return
            progress["step"] = 2
            try:
                import cv2
                device_id = get("capture.device_id", 0)
                cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(device_id)
                ok = cap.isOpened()
                if ok:
                    cap.release()
                if not ok:
                    progress["failed_msg"] = "未识别到采集卡"
                    return
            except Exception:
                progress["failed_msg"] = "未识别到采集卡"

        steps = ["(1/2) 正在检测控制器...", "(2/2) 正在检测采集卡..."]
        self.show_progress(checks, progress, steps)

        if progress["failed_msg"]:
            self.show_message("检测失败", progress["failed_msg"])
            self.set_status(progress["failed_msg"], C_RED)
            return

        self.save_cache(data)
        self.result = data
        self.running = False

    def on_reset(self):
        self.game_combo.selected_index = 0
        self.method_combo.clear()
        self.category_combo.clear()
        self.location_combo.clear()
        self.pokemon_combo.clear()
        self.set_status("已重置", C_TEXT_DIM)

    def on_quit(self):
        self.result = None
        self.running = False

    def collect_inputs(self) -> Optional[dict]:
        data = {}
        data["game"] = self.game_combo.get_value()
        if not data["game"]:
            return None

        data["method"] = self.get_method_en()
        if not data["method"]:
            return None

        data["category"] = self.get_category_en()
        if not data["category"]:
            return None

        data["location"] = self.get_location_en()
        if data["method"] == "Wild" and not data["location"]:
            return None

        pkm_zh = self.pokemon_combo.get_value()
        if not pkm_zh:
            return None
        data["pokemon"] = SPECIES_ZH_TO_EN.get(pkm_zh, pkm_zh)
        if not data["pokemon"]:
            return None

        return data

    def validate(self, data) -> list:
        errors = []
        if data["game"] not in GAME_OPTIONS:
            errors.append(f"无效的 Game: {data['game']}")
        if data["method"] not in METHOD_OPTIONS:
            errors.append(f"无效的 Method: {data['method']}")
        if data["category"] not in METHOD_OPTIONS.get(data["method"], {}).get("categories", []):
            errors.append(f"Category '{data['category']}' 不适用于 Method '{data['method']}'")

        species_id = None
        try:
            species_id = get_species_id(data["pokemon"])
        except Exception:
            errors.append(f"未找到宝可梦: {data['pokemon']}")

        game_ver = GAME_OPTIONS.get(data["game"], "fr_nx")

        if data["method"] == "Wild" and species_id is not None and data["location"]:
            enc = get_encounter_species_list(data["location"], data["category"], game_ver)
            if enc and species_id not in enc:
                avail = ", ".join(get_species_name(s) for s in enc[:10])
                errors.append(f"宝可梦 '{data['pokemon']}' 不在 {game_ver} 的遭遇列表中\n可用: {avail}")

        if data["method"] == "Static" and data["category"]:
            static_list = STATIC_POKEMON_MAP.get(data["category"], [])
            if static_list and data["pokemon"] not in static_list:
                errors.append(
                    f"宝可梦 '{data['pokemon']}' 不在 {data['category']} 遭遇列表中\n"
                    f"可用: {', '.join(static_list)}")

        return errors


# ── script generation ──────────────────────────────────────────────────────────

SAFARI_ZONE_EXTRA_MS = {
    ("Safari Zone Center", "Grass"):   16000,
    ("Safari Zone Center", "Surfing"): 23000,
    ("Safari Zone Center", "Rod"):     18000,
    ("Safari Zone East", "Grass"):     27000,
    ("Safari Zone East", "Surfing"):   39000,
    ("Safari Zone East", "Rod"):       33000,
    ("Safari Zone North", "Grass"):    31000,
    ("Safari Zone North", "Surfing"):  41000,
    ("Safari Zone North", "Rod"):      36000,
    ("Safari Zone West", "Grass"):     38000,
    ("Safari Zone West", "Surfing"):   45000,
    ("Safari Zone West", "Rod"):       40000,
}


def compute_normal_ms_min(category: str, pokemon: str, location: str = "") -> int:
    category = "Rod" if category.endswith("Rod") else category
    if location.startswith("Safari Zone"):
        safari_extra = SAFARI_ZONE_EXTRA_MS[(location, category)]
        return (10000 if category == "Rod" else 5000) + safari_extra
    elif category in ("Rod", "GameCorner"):
        return 10000
    elif category in ("Gift", "Stationary", "Legend", "Fossil", "Event"):
        extra = EXTRA_A_PRESSES.get(pokemon, 0)
        if pokemon == "Ho-Oh":
            extra += 2
        return 5000 + 3000 * max(extra, 0)
    elif category in ("Grass", "Surfing"):
        return 5000
    else:
        raise NotImplementedError(category)


def generate_script(data: dict):
    game_ver  = GAME_OPTIONS[data["game"]]
    method    = data["method"]
    category  = data["category"]
    location  = data["location"] if method == "Wild" else category
    pokemon   = data["pokemon"]
    normal_ms_min = compute_normal_ms_min(category, pokemon, location)

    script = f'''# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.scan import launch

if __name__ == "__main__":
    launch(
        method="{method}",
        category="{category}",
        location="{location}",
        pokemon_species="{pokemon}",
        game_version="{game_ver}",
        normal_ms_min={normal_ms_min},
    )
'''
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "examples", f"scan_custom_{ts}.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    return script_path


def run_script(script_path: str):
    python_exe  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "Python312", "python.exe")
    subprocess.Popen([python_exe, "-u", script_path],
                     cwd=os.path.dirname(os.path.abspath(__file__)))


# ── entry ──────────────────────────────────────────────────────────────────────

def main():
    gui  = ScanGui()
    data = gui.run()
    if data is None:
        print("用户取消。")
        return
    try:
        script_path = generate_script(data)
    except Exception as e:
        print(f"脚本生成失败: {e}")
        return
    run_script(script_path)


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""
RNG 配置 GUI —— 基于 pygame 的乱数配置界面
继承 launch_gui.LaunchGUI 基类，复用公共组件
"""

import json
import os
import sys
from typing import Optional
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launch_gui import (
    LaunchGUI, Label,
    get_font, C_TEXT_DIM,
    C_RED, C_GREEN,
    ROW_H, ROW_GAP, SIDE_PAD, BOX_W, LBL_W,
    connect_controller,
)
from rng.config import RNGConfig, RNGSlot, GameSettings, SessionState
from rng.tenlines_utils import (
    calibration as calibration_api,
    get_encounter_species_list,
    get_species_id,
    get_species_name,
    load_frlg_encounters,
)
from script_utils.hit import EXTRA_A_PRESSES
from easycon.config import get as config_get
from easycon.controller import EasyConController
from assets.game_text import (
    STATIC_CATEGORIES, WILD_CATEGORIES, STATIC_POKEMON_MAP,
    SPECIES_EN_TO_ZH, SPECIES_ZH_TO_EN,
    METHOD_ZH_TO_EN, METHOD_EN_TO_ZH,
    CATEGORY_ZH_TO_EN, CATEGORY_EN_TO_ZH,
    location_to_zh as loc_zh, location_to_en as loc_en,
)

# ── 常量 ──────────────────────────────────────────────
GAME_OPTIONS = {"火红": "fr_nx", "叶绿": "lg_nx"}

METHOD_OPTIONS = {
    "Static": {"categories": STATIC_CATEGORIES, "rng_method": "Static 1"},
    "Wild": {"categories": WILD_CATEGORIES, "rng_method": "All Wild Methods"},
}

DEFAULT_SETTINGS = "Mono | Help | Seed Button: Start | Extra Button: None"
DEFAULT_SETTINGS_ZH = "单声道 | 帮助 | Seed 按键: 开始 | 额外按键: 无"

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "rng_logs", "latest.json")


def get_all_locations() -> dict:
    """合并火红和叶绿的遇敌地点列表"""
    cat_to_locs = {}
    for gv in ("fr_nx", "lg_nx"):
        encounters = load_frlg_encounters(gv)
        for (loc, cat), data in encounters.items():
            if cat not in cat_to_locs:
                cat_to_locs[cat] = set()
            cat_to_locs[cat].add(loc)
    for cat in cat_to_locs:
        cat_to_locs[cat] = sorted(cat_to_locs[cat])
    return cat_to_locs


def read_calibration_limits():
    return {
        "seed_ms_min": config_get("rng.calibration.seed_ms_min", 33000),
        "seed_ms_max": config_get("rng.calibration.seed_ms_max", 72000),
        "tv_ms_min": config_get("rng.calibration.tv_ms_min", 3000),
        "normal_ms_min": config_get("rng.calibration.normal_ms_min", 10000),
    }


# ── RNGGui ─────────────────────────────────────────────────────────────────────

class RNGGui(LaunchGUI):
    TOTAL_SCALE = 3
    WINDOW_TITLE = "EasyCon RNG Configuration"  # 子类 __init__ 可覆盖

    def __init__(self, use_en: bool = False):
        self.use_en = use_en
        if not use_en:
            self.WINDOW_TITLE = "EasyCon RNG 配置"
        self.all_locations = get_all_locations()
        super().__init__()
        self.panel_bg = True
        self.show_instructions()

    def show_instructions(self):
        """显示前置说明"""
        title = "RNG乱数刷闪 - 使用说明"
        msg = (
            "【功能说明】\n"
            "一键乱数刷闪\n"
            "支持：草丛/钓鱼/冲浪/定点/礼物/碎岩\n"
            "不支持：游走/御三家/部分定点\n"
            "\n"
            "【前置准备】\n"
            "0. 游戏：【NS/NS2】&【英文版FRLG】&【TID/SID/Tenlines】\n"
            "1. 硬件：【单片机】&【采集卡】&【联网或显卡】\n"
            "2. 游戏设置：【SOUND】&【BUTTON MODE】\n"
            "3. 游戏道具：【大师球】&【神奇糖果】若干\n"
            "4. 游戏快捷键：【Teachy TV】登录\n"
            "5. 游戏队伍：【队首甜甜香气】&【队尾空位】\n"
            "6. 游戏存档：\n"
            "    【定点】面对宝可梦/礼物/NPC保存\n"
            "    【狩猎区】使用完黄金喷雾&站在收费口精灵球图标上保存\n"
            "    【草丛】站草丛保存【冲浪】冲浪中保存【钓鱼】面对水面保存\n"
            "7. NS回到主页&切换用户&选择好用户 -> 【准备完毕】"
        )
        self.show_message(title, msg)

    def cache_file(self) -> str:
        return CACHE_FILE

    # ── cache ──────────────────────────────────────────────────────────────────

    def apply_cache(self, data: dict):
        """将缓存数据填充到控件"""
        en = self.use_en

        # Game
        game = data.get("game", "")
        if game in self.game_combo.all_options:
            self.game_combo.selected_index = self.game_combo.all_options.index(game)

        # TID / SID
        self.tid_box.text = str(data.get("tid", "58888"))
        self.sid_box.text = str(data.get("sid", "12232"))

        # Settings
        self.settings_box.text = data.get("settings", DEFAULT_SETTINGS if en else DEFAULT_SETTINGS_ZH)

        # Method → Category → Location → Pokemon 级联加载
        method_en = data.get("method", "")
        method_display = method_en if en else METHOD_EN_TO_ZH.get(method_en, method_en)
        if method_display in self.method_combo.all_options:
            self.method_combo.selected_index = self.method_combo.all_options.index(method_display)
        self.method_combo.filter_text = ""
        self.method_combo.apply_filter()

        cats_en = METHOD_OPTIONS.get(method_en, {}).get("categories", [])
        cats_display = cats_en if en else [CATEGORY_EN_TO_ZH.get(c, c) for c in cats_en]
        self.category_combo.set_options(cats_display)

        category_en = data.get("category", "")
        category_display = category_en if en else CATEGORY_EN_TO_ZH.get(category_en, category_en)
        if category_display in self.category_combo.all_options:
            self.category_combo.selected_index = self.category_combo.all_options.index(category_display)
        self.category_combo.filter_text = ""
        self.category_combo.apply_filter()

        if method_en == "Wild" and category_en:
            locs = self.all_locations.get(category_en, [])
            if not en:
                locs = [loc_zh(l) for l in locs]
            self.location_combo.set_options(locs)
        elif method_en == "Static" and category_en:
            loc_val = category_en if en else CATEGORY_EN_TO_ZH.get(category_en, category_en)
            self.location_combo.set_options([loc_val])
        else:
            self.location_combo.set_options([])

        location_en = data.get("location", "")
        location_display = location_en if en else loc_zh(location_en)
        if location_display in self.location_combo.all_options:
            self.location_combo.selected_index = self.location_combo.all_options.index(location_display)
        self.location_combo.filter_text = ""
        self.location_combo.apply_filter()

        self.refresh_pokemon_options()

        pokemon_name = str(data.get("pokemon", "Pikachu"))
        pokemon_display = pokemon_name if en else SPECIES_EN_TO_ZH.get(pokemon_name, pokemon_name)
        if pokemon_display in self.pokemon_combo.all_options:
            self.pokemon_combo.selected_index = self.pokemon_combo.all_options.index(pokemon_display)
            self.pokemon_combo.filter_text = ""
            self.pokemon_combo.apply_filter()

        self.seed_box.text = str(data.get("seed", "B235"))
        self.advances_box.text = str(data.get("advances", "153142"))

    def save_cache(self, data: dict):
        """保存当前参数到 rng_logs/latest.json"""
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── layout ─────────────────────────────────────────────────────────────────

    def build_ui(self):
        en = self.use_en
        y = SIDE_PAD

        # row 1: Game(1) | TID(1) | SID(1)
        game_cb = self.make_combobox(0, 0, 0, ROW_H, list(GAME_OPTIONS.keys()), "火红")
        game_cb.selected_index = 0
        self.game_combo = game_cb

        tid_tb = self.make_textbox(0, 0, 0, ROW_H, "58888")
        self.tid_box = tid_tb

        sid_tb = self.make_textbox(0, 0, 0, ROW_H, "12232")
        self.sid_box = sid_tb

        y = self.add_row(y, [
            (1, "Game:",   game_cb, {}),
            (1, "TID:",    tid_tb,  {}),
            (1, "SID:",    sid_tb,  {}),
        ])

        # row 2: Settings(2) | Method(1)
        settings_label = "Settings:" if en else "设置:"
        method_label   = "Method:" if en else "方法:"
        method_opts = list(METHOD_OPTIONS.keys())
        if not en:
            method_opts = [METHOD_EN_TO_ZH.get(m, m) for m in method_opts]

        settings_tb = self.make_textbox(0, 0, 0, ROW_H, DEFAULT_SETTINGS if en else DEFAULT_SETTINGS_ZH)
        self.settings_box = settings_tb

        method_cb = self.make_combobox(0, 0, 0, ROW_H, method_opts, "Wild" if en else "野生",
                               on_change=self.on_method_change)
        self.method_combo = method_cb

        y = self.add_row(y, [
            (2, settings_label, settings_tb, {}),
            (1, method_label,   method_cb,   {}),
        ])

        # row 3: Category(1) | Location(2)
        cat_label = "Category:" if en else "分类:"
        loc_label = "Location:" if en else "地点:"

        cat_cb = self.make_combobox(0, 0, 0, ROW_H, [], "Grass" if en else "草丛",
                                    on_change=self.on_category_change)
        self.category_combo = cat_cb

        loc_cb = self.make_combobox(0, 0, 0, ROW_H, [],
                                    "Search location..." if en else "搜索地点...",
                                    on_change=self.on_location_change)
        self.location_combo = loc_cb

        y = self.add_row(y, [
            (1, cat_label, cat_cb, {}),
            (2, loc_label, loc_cb, {}),
        ])

        # row 4: Pokemon(1) | Seed(1) | Adv.(1)
        pokemon_label = "Pokemon:" if en else "宝可梦:"
        pokemon_ph    = "Search Pokemon..." if en else "搜索宝可梦..."

        pkm_cb = self.make_combobox(0, 0, 0, ROW_H, [], pokemon_ph)
        self.pokemon_combo = pkm_cb

        seed_tb = self.make_textbox(0, 0, 0, ROW_H, "B235")
        self.seed_box = seed_tb

        adv_tb = self.make_textbox(0, 0, 0, ROW_H, "153142")
        self.advances_box = adv_tb

        y = self.add_row(y, [
            (1, pokemon_label, pkm_cb,  {}),
            (1, "Seed:",       seed_tb, {}),
            (1, "Adv.:",       adv_tb,  {}),
        ])

        # row 5: URL (wide label) + parse button
        url_label_text = "URL (ten-lines calibration):" if en else "URL (ten-lines 校准):"
        url_ph = ("https://lincoln-lm.github.io/ten-lines/?..."
                  if en else "https://www.xiaoyubook.net/ten-lines/?...")
        url_label_w = 160
        btn_w2 = 90
        total_w = (BOX_W + SIDE_PAD + LBL_W) * self.TOTAL_SCALE + SIDE_PAD
        url_total_w = total_w - url_label_w - SIDE_PAD * 3 - btn_w2

        url_label = Label(SIDE_PAD, y, url_label_w, ROW_H, url_label_text)
        self.widgets.append(url_label)

        self.url_box = self.make_textbox(SIDE_PAD + url_label_w, y,
                                         url_total_w, ROW_H, url_ph)
        self.make_button(SIDE_PAD + url_label_w + url_total_w + SIDE_PAD,
                         y, btn_w2, ROW_H, "智能识别", self.on_parse_url)

        y += ROW_H + ROW_GAP

        # button row
        y = self.add_button_row(y, [
            ("确定", self.on_confirm),
            ("默认", self.on_default),
            ("重置", self.on_reset),
            ("退出", self.on_quit),
        ])

        self.H = self.final_height(y)
        self.resize_to_fit()

        self.status_text  = ""
        self.status_color = C_TEXT_DIM
        self.status_font  = get_font(13)

    # ── cascade ────────────────────────────────────────────────────────────────

    def get_pokemon_options(self, method: str, category: str, location: str) -> list:
        if method == "Static" and category:
            pokemon_list = STATIC_POKEMON_MAP.get(category, [])
            if not self.use_en:
                return [SPECIES_EN_TO_ZH.get(p, p) for p in pokemon_list]
            return pokemon_list
        if method == "Wild" and location and category:
            game_label = self.game_combo.get_value()
            game_version = GAME_OPTIONS.get(game_label, "fr_nx")
            species_ids = get_encounter_species_list(location, category, game_version)
            if not self.use_en:
                return [SPECIES_EN_TO_ZH.get(get_species_name(s), str(s)) for s in species_ids]
            return [get_species_name(s) for s in species_ids]
        return []

    def cascade_reset(self, level: int):
        if level <= 1:
            cats = self.category_combo.all_options
            if cats:
                self.category_combo.selected_index = 0
            else:
                self.category_combo.selected_index = -1
            self.category_combo.filter_text = ""
            self.category_combo.apply_filter()

        if level <= 2:
            method_en = self.get_method_en()
            cat_en = self.get_category_en()
            if method_en == "Wild" and cat_en:
                locs = self.all_locations.get(cat_en, [])
                if not self.use_en:
                    locs = [loc_zh(l) for l in locs]
                self.location_combo.set_options(locs, 0 if locs else -1)
            elif method_en == "Static" and cat_en:
                loc_val = cat_en if self.use_en else CATEGORY_EN_TO_ZH.get(cat_en, cat_en)
                self.location_combo.set_options([loc_val], 0)
            else:
                self.location_combo.set_options([])

        self.refresh_pokemon_options()

    def refresh_pokemon_options(self):
        method_en = self.get_method_en()
        cat_en = self.get_category_en()
        loc_en_val = self.get_location_en()
        opts = self.get_pokemon_options(method_en, cat_en, loc_en_val)
        self.pokemon_combo.set_options(opts, 0 if opts else -1)

    def get_method_en(self) -> str:
        val = self.method_combo.get_value()
        if not self.use_en:
            return METHOD_ZH_TO_EN.get(val, val)
        return val

    def get_category_en(self) -> str:
        val = self.category_combo.get_value()
        if not self.use_en:
            return CATEGORY_ZH_TO_EN.get(val, val)
        return val

    def get_location_en(self) -> str:
        val = self.location_combo.get_value()
        if not self.use_en:
            return loc_en(val)
        return val

    def on_method_change(self):
        method_en = self.get_method_en()
        cats = METHOD_OPTIONS.get(method_en, {}).get("categories", [])
        if not self.use_en:
            cats = [CATEGORY_EN_TO_ZH.get(c, c) for c in cats]
        self.category_combo.set_options(cats, 0 if cats else -1)
        self.cascade_reset(level=1)

    def on_category_change(self):
        self.cascade_reset(level=2)

    def on_location_change(self):
        self.refresh_pokemon_options()

    # ── buttons ────────────────────────────────────────────────────────────────

    def on_confirm(self):
        data = self.collect_inputs()
        if data is None:
            self.set_status("请填写所有必填字段。" if not self.use_en else "Please fill all required fields.", C_RED)
            return

        en = self.use_en

        # ── 3 步并行检测 ──
        def check_params(results, idx):
            errors = self.validate(data)
            if errors:
                results[idx] = (False, errors[0])
            else:
                results[idx] = (True, "")

        def check_controller(results, idx):
            try:
                c = EasyConController()
                if not c.list_ports() or not c.connect(timeout=2.0):
                    results[idx] = (False, "未识别到可用控制器")
                    return
                c.disconnect()
                results[idx] = (True, "")
            except Exception:
                results[idx] = (False, "未识别到可用控制器")

        def check_capture(results, idx):
            try:
                import cv2
                device_id = config_get("capture.device_id", 0)
                cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(device_id)
                ok = cap.isOpened()
                if ok:
                    cap.release()
                if not ok:
                    results[idx] = (False,
                        "Capture card not found" if en else "未识别到采集卡")
                else:
                    results[idx] = (True, "")
            except Exception:
                results[idx] = (False,
                    "Capture card not found" if en else "未识别到采集卡")

        title = "Checking" if en else "正在检测"
        results = self.show_parallel_progress([
            ("参数校验",   check_params),
            ("控制器检测", check_controller),
            ("采集卡检测", check_capture),
        ], title=title)

        # 被中断
        if not self.running:
            return

        # 收集失败项
        failures = [
            (name, msg) for (name, _), (ok, msg) in
            zip([("参数校验", None), ("控制器检测", None), ("采集卡检测", None)],
                results)
            if ok is not None and not ok
        ]
        if failures:
            msgs = [f"• {name}: {msg}" for name, msg in failures]
            self.show_message(
                "检测失败" if not en else "Detection Failed",
                "\n".join(msgs))
            self.set_status(failures[0][1], C_RED)
            return

        self.save_cache(data)
        self.result = data
        self.running = False

    def on_reset(self):
        self.game_combo.selected_index = 0
        self.tid_box.clear()
        self.sid_box.clear()
        self.settings_box.clear()
        self.method_combo.clear()
        self.category_combo.clear()
        self.location_combo.clear()
        self.pokemon_combo.clear()
        self.seed_box.clear()
        self.advances_box.clear()
        self.url_box.clear()
        self.set_status("已重置", C_TEXT_DIM)

    def on_quit(self):
        self.result = None
        self.running = False

    def on_parse_url(self):
        url = self.url_box.get_value()
        if not url:
            self.set_status("请先输入 URL", C_RED)
            return

        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            p = {k: v[0] for k, v in params.items()}
        except Exception:
            self.set_status("URL 解析失败", C_RED)
            return

        errors = []

        game_rev = {"fr_nx": "火红", "lg_nx": "叶绿"}
        game = game_rev.get(p.get("game", ""), "")
        if game in self.game_combo.all_options:
            self.game_combo.selected_index = self.game_combo.all_options.index(game)
        else:
            errors.append("未识别的 game 参数")

        try:
            tid = int(p.get("trainerID", ""))
            if 0 <= tid <= 65535:
                self.tid_box.text = str(tid)
            else:
                errors.append(f"TID 越界: {tid}")
        except ValueError:
            errors.append("trainerID 无效")

        try:
            sid = int(p.get("secretID", ""))
            if 0 <= sid <= 65535:
                self.sid_box.text = str(sid)
            else:
                errors.append(f"SID 越界: {sid}")
        except ValueError:
            errors.append("secretID 无效")

        seed = p.get("targetInitialSeed", "").upper()
        try:
            int(seed, 16)
            self.seed_box.text = seed
        except ValueError:
            errors.append("targetInitialSeed 无效")

        try:
            adv_min = int(p.get("advancesMin", "0"))
            adv_max = int(p.get("advancesMax", "0"))
            advances = (adv_min + adv_max) // 2
            if p.get("teachyTVMode", "").lower() == "true":
                try:
                    ttv_min = int(p.get("ttvAdvancesMin", "0"))
                    ttv_max = int(p.get("ttvAdvancesMax", "0"))
                    ttv_advances = (ttv_min + ttv_max) // 2
                    advances = advances + 312 * ttv_advances
                except ValueError:
                    pass
            if advances < 0:
                errors.append("advances 计算为负数")
            else:
                self.advances_box.text = str(advances)
        except ValueError:
            errors.append("advancesMin/advancesMax 无效")

        sound_map = {"mono": "Mono", "stereo": "Stereo"}
        sound = sound_map.get(p.get("sound", "").lower(), "Mono")

        btn_mode_map = {"a": "L=A", "h": "Help", "r": "LR"}
        btn_mode = btn_mode_map.get(p.get("buttonMode", "").lower(), "L=A")

        seed_btn_map = {"a": "A", "start": "Start", "l": "L (L=A)"}
        seed_btn = seed_btn_map.get(p.get("button", "").lower(), "A")

        held_map = {
            "none": "None", "startup_select": "Startup Select", "startup_a": "Startup A",
            "blackout_r": "Blackout R", "blackout_a": "Blackout A",
            "blackout_l": "Blackout L", "blackout_al": "Blackout A+L",
        }
        held = held_map.get(p.get("heldButton", "").lower(), "None")

        settings = f"{sound} | {btn_mode} | Seed Button: {seed_btn} | Extra Button: {held}"
        self.settings_box.text = settings

        if errors:
            self.set_status("部分字段解析成功: " + "; ".join(errors), C_RED)
        else:
            self.set_status("URL 智能识别完成", C_GREEN)

    def on_default(self):
        en = self.use_en
        self.game_combo.selected_index = 0

        self.tid_box.text = "58888"
        self.tid_box.focused = False

        self.sid_box.text = "12232"
        self.sid_box.focused = False

        self.settings_box.text = DEFAULT_SETTINGS if en else DEFAULT_SETTINGS_ZH
        self.settings_box.focused = False

        self.method_combo.selected_index = 1
        self.method_combo.filter_text = ""
        self.method_combo.apply_filter()
        self.on_method_change()

        self.category_combo.selected_index = 0
        self.category_combo.filter_text = ""
        self.category_combo.apply_filter()
        self.on_category_change()

        default_loc = "Viridian Forest" if en else "常青森林"
        if default_loc in self.location_combo.all_options:
            self.location_combo.selected_index = self.location_combo.all_options.index(default_loc)
            self.location_combo.filter_text = ""
            self.location_combo.apply_filter()

        self.refresh_pokemon_options()
        default_pkm = "Pikachu" if en else "皮卡丘"
        if default_pkm in self.pokemon_combo.all_options:
            self.pokemon_combo.selected_index = self.pokemon_combo.all_options.index(default_pkm)
            self.pokemon_combo.filter_text = ""
            self.pokemon_combo.apply_filter()

        self.seed_box.text = "B235"
        self.seed_box.focused = False

        self.advances_box.text = "153142"
        self.advances_box.focused = False

        self.set_status("已填充默认值", C_TEXT_DIM)

    def collect_inputs(self) -> Optional[dict]:
        data = {}

        data["game"] = self.game_combo.get_value()
        if not data["game"]:
            return None

        tid_str = self.tid_box.get_value()
        if not tid_str:
            return None
        try:
            data["tid"] = int(tid_str)
        except ValueError:
            return None

        sid_str = self.sid_box.get_value()
        if not sid_str:
            return None
        try:
            data["sid"] = int(sid_str)
        except ValueError:
            return None

        settings_str = self.settings_box.get_value()
        data["settings"] = settings_str if settings_str else (
            DEFAULT_SETTINGS if self.use_en else DEFAULT_SETTINGS_ZH)

        data["method"] = self.get_method_en()
        if not data["method"]:
            return None

        data["category"] = self.get_category_en()
        if not data["category"]:
            return None

        data["location"] = self.get_location_en()
        if self.get_method_en() == "Wild" and not data["location"]:
            return None

        pokemon_val = self.pokemon_combo.get_value()
        if not self.use_en:
            pokemon_val = SPECIES_ZH_TO_EN.get(pokemon_val, pokemon_val)
        data["pokemon"] = pokemon_val
        if not data["pokemon"]:
            return None

        seed_str = self.seed_box.get_value()
        if not seed_str:
            return None
        data["seed"] = seed_str.strip().upper()

        adv_str = self.advances_box.get_value()
        if not adv_str:
            return None
        try:
            data["advances"] = int(adv_str)
        except ValueError:
            return None

        return data

    def validate(self, data: dict) -> list:
        errors = []

        if data["game"] not in GAME_OPTIONS:
            errors.append(f"无效的 Game: {data['game']}")
        if not (0 <= data["tid"] <= 65535):
            errors.append(f"TID 必须在 0-65535 之间")
        if not (0 <= data["sid"] <= 65535):
            errors.append(f"SID 必须在 0-65535 之间")
        if data["method"] not in METHOD_OPTIONS:
            errors.append(f"无效的 Method: {data['method']}")
        if data["category"] not in METHOD_OPTIONS.get(data["method"], {}).get("categories", []):
            errors.append(f"Category '{data['category']}' 不适用于 Method '{data['method']}'")

        try:
            game_settings = GameSettings.from_string(data["settings"])
        except Exception as e:
            errors.append(f"Settings 格式错误: {e}")
            game_settings = None

        try:
            seed_int = int(data["seed"], 16)
            if not (0 <= seed_int <= 0xFFFF):
                errors.append(f"Seed 必须在 0x0000-0xFFFF 之间")
        except ValueError:
            errors.append(f"Seed 必须是有效的十六进制数")
            seed_int = None

        if data["advances"] < 0:
            errors.append(f"Advances 不能为负数")

        species_id = None
        try:
            species_id = get_species_id(data["pokemon"])
        except ValueError:
            try:
                from assets.game_text import species_to_en as get_species_en_name
                en_name = get_species_en_name(data["pokemon"])
                species_id = get_species_id(en_name)
                data["pokemon"] = en_name
            except Exception:
                pass
        if species_id is None:
            errors.append(f"未找到宝可梦: {data['pokemon']}")

        if data["method"] == "Wild" and species_id is not None and data["location"]:
            game_ver = GAME_OPTIONS.get(data["game"], "fr_nx")
            encounter_species = get_encounter_species_list(data["location"], data["category"], game_ver)
            if encounter_species and species_id not in encounter_species:
                avail = ", ".join(get_species_name(s) for s in encounter_species[:10])
                errors.append(
                    f"宝可梦 '{data['pokemon']}' 不在遭遇列表中\n可用: {avail}"
                )

        if data["method"] == "Static" and data["category"]:
            static_pokemon = STATIC_POKEMON_MAP.get(data["category"], [])
            en_name = data.get("pokemon", "")
            if static_pokemon and en_name not in static_pokemon:
                errors.append(
                    f"宝可梦 '{data['pokemon']}' 不在 {data['category']} 遭遇列表中\n可用: {', '.join(static_pokemon)}"
                )

        if errors:
            return errors

        game_version = GAME_OPTIONS[data["game"]]
        rng_method = METHOD_OPTIONS[data["method"]]["rng_method"]
        location = data["location"] if data["method"] == "Wild" else data["category"]

        try:
            cfg = RNGConfig(
                game_version=game_version,
                trainer_id=data["tid"],
                secret_id=data["sid"],
                game_settings=game_settings,
                pokemon_species=data["pokemon"],
                rng_category=data["category"],
                rng_location=location,
                rng_method=rng_method,
                target=RNGSlot(seed_int, 0, data["advances"]),
                seed_bias=-4000,
                advances_bias=-10000,
                normal_ms_min=compute_normal_ms_min(data["category"], data["pokemon"], location),
            )
        except KeyError as e:
            errors.append(f"Seed {data['seed']} 不在种子表中")
            return errors
        except Exception as e:
            errors.append(f"创建 RNG 配置失败: {e}")
            return errors

        limits = read_calibration_limits()
        s = cfg.schedule
        if s.seed_ms < limits["seed_ms_min"]:
            errors.append(f"Seed 时间过短 ({s.seed_ms}ms < {limits['seed_ms_min']}ms)")
        if s.seed_ms > limits["seed_ms_max"]:
            errors.append(f"Seed 时间过长 ({s.seed_ms}ms > {limits['seed_ms_max']}ms)")
        if s.advances_ms_tv > 0 and s.advances_ms_tv < limits["tv_ms_min"]:
            errors.append(f"TV 时间过短 ({s.advances_ms_tv}ms < {limits['tv_ms_min']}ms)")
        if s.advances_ms_normal < limits["normal_ms_min"]:
            errors.append(f"Normal 时间过短 ({s.advances_ms_normal}ms < {limits['normal_ms_min']}ms)")

        try:
            targetresults = calibration_api(
                game=game_version, tid=data["tid"], sid=data["sid"],
                method=rng_method, category=data["category"], location=location,
                pokemon=data["pokemon"], seed=f"{seed_int:04X}", advances=data["advances"],
                settings=game_settings, seed_bias=0, advances_bias=0,
            )
            is_shiny = any(r.shiny not in ("", "None") for r in targetresults)
            if not is_shiny:
                errors.append("目标不是闪光! 请确认 Seed/Advances 是否正确。")
        except Exception as e:
            errors.append(f"闪光校验失败: {e}")

        return errors


# ── 脚本生成与运行 ────────────────────────────────────

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
        return (15000 if category == "Rod" else 10000) + safari_extra
    elif category in ("Rod", "GameCorner"):
        return 15000
    elif category in ("Gift", "Stationary", "Legend", "Fossil", "Event"):
        extra = EXTRA_A_PRESSES.get(pokemon, 0)
        if pokemon == "Ho-Oh":
            extra += 2
        return 10000 + 3000 * max(extra, 0)
    elif category == "RockSmash":
        return 13000  # 碎岩：1 次额外 A 按键 (10000 + 3000 * 1)
    elif category in ("Grass", "Surfing"):
        return 10000
    else:
        raise NotImplementedError(category)


# ── entry ──────────────────────────────────────────────────────────────────────

def main():
    """入口：默认中文，支持 --en 参数切换英文"""
    use_en = "--en" in sys.argv
    gui = RNGGui(use_en=use_en)
    data = gui.run()
    if data is None:
        print("Cancelled." if use_en else "用户取消。")
        return

    game_version = GAME_OPTIONS[data["game"]]
    rng_method = METHOD_OPTIONS[data["method"]]["rng_method"]
    location = data["location"] if data["method"] == "Wild" else data["category"]
    seed_hex = data["seed"].upper()
    normal_ms_min = compute_normal_ms_min(data["category"], data["pokemon"], location)

    cfg = RNGConfig(
        game_version=game_version,
        trainer_id=data['tid'],
        secret_id=data['sid'],
        game_settings=GameSettings.from_string(data['settings']),
        pokemon_species=data['pokemon'],
        rng_category=data['category'],
        rng_location=location,
        rng_method=rng_method,
        target=RNGSlot(int(seed_hex, 16), 0, data['advances']),
        seed_bias=-4000,
        advances_bias=-10000,
        normal_ms_min=normal_ms_min,
    )
    state = SessionState()

    # 连接 controller 一次，传递给 rng_launch 复用
    controller = connect_controller()
    if controller is None:
        print("无法连接控制器，请检查硬件。")
        return

    from examples.rng import launch as rng_launch
    rng_launch(cfg, state, controller=controller)


if __name__ == "__main__":
    main()
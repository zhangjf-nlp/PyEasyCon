# -*- coding: utf-8 -*-
"""
Training GUI —— 基于 pygame 的EV训练配置界面
通过 run_training.bat 启动
"""

import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from launch_gui import LaunchGUI, ComboBox, C_TEXT_DIM, C_RED, ROW_H, ROW_GAP, SIDE_PAD, connect_controller

from examples.training import TrainingConfig, heal2grass_route_map, get_location_basepoints
from assets.game_text import STAT_ZH_MAP, ALL_STATS, location_to_zh, location_to_en

# 游戏版本选项（参考 rng/scan GUI）
GAME_OPTIONS = {"火红": "fr_nx", "叶绿": "lg_nx"}


class TrainingGUI(LaunchGUI):
    TOTAL_SCALE = 2
    WINDOW_TITLE = "EasyCon EV训练配置"

    CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "training_logs", "latest.json")

    def __init__(self):
        super().__init__()
        self.show_instructions()

    def cache_file(self) -> str:
        return self.CACHE_FILE

    def show_instructions(self):
        """显示前置说明"""
        title = "刷怪升级 - 使用说明"
        msg = (
            "【功能说明】\n"
            "自动循环刷怪以获取努力值、经验、捡拾道具\n"
            "仅支持部分地点\n"
            "\n"
            "【前置准备】\n"
            "0. 游戏：【NS/NS2】&【英文版FRLG】\n"
            "1. 硬件：【单片机】&【采集卡】\n"
            "2. 游戏队伍：【队首单刷野怪】&【队尾甜甜香气】&【喵喵捡拾】\n"
            "3. 站在【宝可梦中心】门口面朝下 -> 【准备完毕】"
        )
        self.show_message(title, msg)

    def build_ui(self):
        y = SIDE_PAD

        # row 1: Game Version(1) | Location(1)
        game_opts = list(GAME_OPTIONS.keys())
        game_cb = self.make_combobox(0, 0, 0, ROW_H, game_opts, placeholder="选择版本...")
        self.game_combo = game_cb
        game_cb.set_on_change(self.on_location_change)

        location_opts = [location_to_zh(k) for k in heal2grass_route_map.keys()]
        loc_cb = self.make_combobox(0, 0, 0, ROW_H, location_opts, placeholder="选择地点...")
        self.location_combo = loc_cb
        loc_cb.set_on_change(self.on_location_change)

        y = self.add_row(y, [
            (1, "版本:", game_cb, {}),
            (1, "地点:", loc_cb, {}),
        ])

        # row 2: Stat1(1) | Stat2(1)
        stat1_cb = self.make_combobox(0, 0, 0, ROW_H, [], placeholder="属性1...")
        self.stat1_combo = stat1_cb
        stat1_cb.set_on_change(self.on_stat1_change)

        stat2_cb = self.make_combobox(0, 0, 0, ROW_H, [], placeholder="属性2 (可选)")
        self.stat2_combo = stat2_cb

        y = self.add_row(y, [
            (1, "属性1:", stat1_cb, {}),
            (1, "属性2:", stat2_cb, {}),
        ])

        # button row
        y = self.add_button_row(y, [
            ("确定", self.on_confirm),
            ("重置", self.on_reset),
            ("退出", self.on_quit),
        ])

        self.H = self.final_height(y)
        self.resize_to_fit()

    # ── cascade ────────────────────────────────────────────────────────────────

    def on_location_change(self):
        """location 改变后，刷新 stat1 的选项"""
        location_display = self.location_combo.get_value()
        if not location_display:
            self.stat1_combo.set_options([])
            self.stat2_combo.set_options([])
            return

        # 将显示名称转换为内部名称
        location = location_to_en(location_display)
        game_version = GAME_OPTIONS.get(self.game_combo.get_value(), "fr_nx")
        basepoints = get_location_basepoints(location, game_version)
        stat_options = [STAT_ZH_MAP.get(s, s) for s in basepoints]
        self.stat1_combo.set_options(stat_options, 0 if stat_options else -1)
        self.on_stat1_change()

    def on_stat1_change(self):
        """stat1 改变后，刷新 stat2 的选项"""
        stat1_zh = self.stat1_combo.get_value()
        location_display = self.location_combo.get_value()

        if not stat1_zh or not location_display:
            self.stat2_combo.set_options([])
            return

        # 将显示名称转换为内部名称
        location = location_to_en(location_display)
        game_version = GAME_OPTIONS.get(self.game_combo.get_value(), "fr_nx")
        basepoints = get_location_basepoints(location, game_version)
        stat_options = [STAT_ZH_MAP.get(s, s) for s in basepoints]

        available_stats = [s for s in stat_options if s != stat1_zh]
        self.stat2_combo.set_options(["(空)"] + available_stats, 0)

    # ── inputs ────────────────────────────────────────────────────────────────

    def collect_inputs(self) -> Optional[dict]:
        data = {}
        game_label = self.game_combo.get_value()
        if not game_label:
            return None
        data["game"] = game_label
        location_display = self.location_combo.get_value()
        if not location_display:
            return None
        # 将显示名称转换为内部名称
        data["location"] = location_to_en(location_display)
        data["stat1"] = self.stat1_combo.get_value()
        if not data["stat1"]:
            return None
        data["stat2"] = self.stat2_combo.get_value()
        return data

    def validate(self, data: dict) -> list:
        errors = []
        if data["location"] not in heal2grass_route_map:
            errors.append(f"无效的地点: {data['location']}")
        stat1_zh = data.get("stat1", "")
        if stat1_zh not in [STAT_ZH_MAP.get(s, s) for s in ALL_STATS]:
            errors.append(f"无效的属性1: {stat1_zh}")
        stat2_zh = data.get("stat2", "")
        if stat2_zh and stat2_zh != "(空)":
            if stat2_zh not in [STAT_ZH_MAP.get(s, s) for s in ALL_STATS]:
                errors.append(f"无效的属性2: {stat2_zh}")
        return errors

    def apply_cache(self, data: dict):
        game = data.get("game", "火红")
        if game in self.game_combo.all_options:
            self.game_combo.selected_index = self.game_combo.all_options.index(game)
        self.game_combo.filter_text_ = ""
        self.game_combo.apply_filter()

        loc_internal = data.get("location", "")
        # 将内部名称转换为显示名称
        loc_display = location_to_zh(loc_internal)
        if loc_display in self.location_combo.all_options:
            self.location_combo.selected_index = self.location_combo.all_options.index(loc_display)
        self.location_combo.filter_text_ = ""
        self.location_combo.apply_filter()
        self.on_location_change()

        stat1 = data.get("stat1", "")
        if stat1 in self.stat1_combo.all_options:
            self.stat1_combo.selected_index = self.stat1_combo.all_options.index(stat1)
        self.stat1_combo.filter_text_ = ""
        self.stat1_combo.apply_filter()
        self.on_stat1_change()

        stat2 = data.get("stat2", "")
        if stat2 in self.stat2_combo.all_options:
            self.stat2_combo.selected_index = self.stat2_combo.all_options.index(stat2)
        self.stat2_combo.filter_text_ = ""
        self.stat2_combo.apply_filter()

    # ── buttons ────────────────────────────────────────────────────────────────

    def on_reset(self):
        self.game_combo.clear()
        self.location_combo.clear()
        self.stat1_combo.clear()
        self.stat2_combo.clear()
        self.set_status("已重置", C_TEXT_DIM)

    def on_confirm(self):
        data = self.collect_inputs()
        if data is None:
            self.set_status("请填写所有必填字段。", C_RED)
            return
        errors = self.validate(data)
        if errors:
            self.set_status(errors[0], C_RED)
            return
        self.save_cache(data)
        self.result = data
        self.running = False

    def save_cache(self, data: dict):
        self.save_cache_impl(data)


# ── helpers ────────────────────────────────────────────────────────────────────

def zh_to_en_stat(zh: str) -> str:
    for en, z in STAT_ZH_MAP.items():
        if z == zh:
            return en
    return zh


# ── entry ──────────────────────────────────────────────────────────────────────

def main():
    gui = TrainingGUI()
    data = gui.run()
    if data is None:
        print("用户取消。")
        return

    game_version = GAME_OPTIONS.get(data["game"], "fr_nx")
    location = data["location"]
    stat1_en = zh_to_en_stat(data["stat1"])
    stat2_en = zh_to_en_stat(data["stat2"]) if data.get("stat2") and data["stat2"] != "(空)" else None

    cfg = TrainingConfig(
        game_version=game_version,
        location=location,
        stat1=stat1_en,
        stat2=stat2_en,
    )

    # 连接 controller 一次，传递给 launch 复用
    controller = connect_controller()
    if controller is None:
        print("无法连接控制器，请检查硬件。")
        return

    from examples.training import launch
    launch(cfg, controller=controller)


if __name__ == "__main__":
    main()

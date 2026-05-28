# -*- coding: utf-8 -*-
import sys
import os
import json

import cv2
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from typing import List

from easycon.context import ScriptContext
from gui import run_script
from script_utils.hit import sleep
from rng.tenlines_utils import get_encounter
from vision.sprite import identify_pokemon, preload_sprites

_BASEPOINTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "sprite_basepoints", "basepoints.json"
)
with open(_BASEPOINTS_PATH, "r", encoding="utf-8") as f:
    _BASEPOINTS = json.load(f)

_STAT_ALIAS = {
    "hp": "hp", "attack": "attack", "atk": "attack",
    "defense": "defense", "def": "defense",
    "sp_atk": "sp_atk", "spatk": "sp_atk", "spa": "sp_atk",
    "sp_def": "sp_def", "spdef": "sp_def", "spd": "sp_def",
    "speed": "speed", "spe": "speed",
}

_STAT_ZH = {
    "hp": "HP", "attack": "攻击", "defense": "防御",
    "sp_atk": "特攻", "sp_def": "特防", "speed": "速度",
}

_ALL_STATS = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]


def get_bp(sid):
    return _BASEPOINTS.get(str(sid), {})


def get_name(sid):
    bp = get_bp(sid)
    return bp.get("zh_name", f"#{sid}")


def format_ev(bp, stat_keys=None):
    keys = stat_keys if stat_keys is not None else _ALL_STATS
    return ", ".join(f"{_STAT_ZH[k]}+{bp.get(k, 0)}" for k in keys if bp.get(k, 0) > 0)


def in_wild(ctx: ScriptContext) -> bool:
    return ctx.search_label("FRLG草丛", 90) or ctx.search_label("FRLG对话", 90) \
        or ctx.search_label("FRLG水面", 90) or ctx.search_label("FRLG洞穴", 90)


@dataclass
class EVTrainConfig:
    location: str = "Route 1"
    category: str = "Grass"
    base_points: List[str] = None
    game_version: str = "frlg"

    def __post_init__(self):
        if self.base_points is None:
            self.base_points = ["speed"]


def resolve_target_species(config: EVTrainConfig):
    stat_keys = []
    for bp_item in config.base_points:
        k = _STAT_ALIAS.get(bp_item.lower())
        if k is None:
            raise ValueError(f"未知的基础点数类型: {bp_item}，支持: HP/攻击/防御/特攻/特防/速度")
        stat_keys.append(k)

    if "safari" in config.location.lower():
        raise RuntimeError("沙湖乐园 (Safari Zone) 暂不支持！")

    encounter = get_encounter(config.location, config.category)
    if encounter is None:
        raise RuntimeError(
            f"未找到遇敌数据: location={config.location}, category={config.category}\n"
            f"支持的 category: Grass / Surfing / OldRod / GoodRod / SuperRod"
        )

    encounter_species = {slot["species"] for slot in encounter.get("slots", []) if "species" in slot}
    stat_set = set(stat_keys)

    targets = []
    for sid in sorted(encounter_species):
        bp = get_bp(sid)
        pkm_stats = {k for k in _ALL_STATS if bp.get(k, 0) > 0}
        if pkm_stats and pkm_stats.issubset(stat_set):
            targets.append(sid)

    if not targets:
        lines = "\n".join(
            f"  {get_name(sid)} (#{sid}) → {format_ev(get_bp(sid))}"
            for sid in sorted(encounter_species)
        )
        raise RuntimeError(
            f"在 {config.location}/{config.category} 中没有找到"
            f"基础点数是 [{', '.join(_STAT_ZH[k] for k in stat_keys)}] 子集的宝可梦！\n"
            f"该地区存在的宝可梦及基础点数:\n{lines}"
        )

    return targets, sorted(encounter_species), stat_keys


def search_and_take_meowth_items(ctx: ScriptContext) -> None:
    for _ in range(3):
        if not ctx.search_label("FRLG喵喵携带物", 95):
            continue
        ctx.log("检测到喵喵携带物")
        for __ in range(7):
            ctx.press("DOWN")
            sleep(0.5)
            for ___ in range(3):
                if ctx.search_label("FRLG喵喵携带物选中", 95):
                    break
            else:
                continue
            ctx.press("A")
            sleep(0.8)
            ctx.press("UP")
            sleep(0.8)
            ctx.press("UP")
            sleep(0.8)
            ctx.press("A")
            sleep(0.8)
            ctx.press("DOWN")
            sleep(0.8)
            ctx.press("A")
            sleep(1.5)
            text = ctx.ocr_taken_item(ctx.get_frame())
            ctx.log(f"拾取道具: {text}" if text else "拾取道具: (识别失败)")
            sleep(0.5)
            ctx.press("B")
            sleep(1.0)


def navigate_to_sweet_scent(ctx: ScriptContext) -> bool:
    ctx.press("X")
    sleep(1.0)

    for _ in range(10):
        if ctx.search_label("FRLG关键词POKeMON选中", 98):
            break
        ctx.press("DOWN")
        sleep(0.8)
    else:
        ctx.log("无法定位到POKeMON菜单")
        return False

    ctx.press("A")
    sleep(2.0)

    # 判断是否有喵喵携带物品
    search_and_take_meowth_items(ctx)

    ctx.press("UP")
    sleep(0.5)
    ctx.press("UP")
    sleep(0.5)
    ctx.press("A")
    sleep(1.0)

    if not ctx.search_label("FRLG关键词SweetScent", 80):
        ctx.log("队末宝可梦未学习甜甜香气")

    for _ in range(5):
        if ctx.search_label("FRLG关键词SweetScent", 99):
            break
        else:
            ctx.press("DOWN")
            sleep(0.5)
    else:
        ctx.log("队末宝可梦未找到甜甜香气")
        sleep(3600)
        return False

    ctx.press("A")
    sleep(8.0)
    return True


def use_sweet_scent(ctx: ScriptContext) -> bool:
    ctx.log("使用甜甜香气...")
    if not navigate_to_sweet_scent(ctx):
        return False
    for _ in range(10):
        sleep(0.5)
        if ctx.search_label("FRLG野怪血条", 90):
            return True
    ctx.log("甜甜香气未触发遇敌")
    return False


def run_away(ctx: ScriptContext) -> None:
    ctx.log("逃跑...")
    for _ in range(15):
        ctx.press("B")
        sleep(0.3)
        ctx.press("DOWN")
        sleep(0.3)
        ctx.press("RIGHT")
        sleep(0.3)
        if ctx.search_label("FRLG逃跑", 90):
            ctx.press("A")
            sleep(1.0)
            break
    for _ in range(30):
        sleep(0.5)
        if in_wild(ctx):
            return
        ctx.press("B")
        sleep(0.3)


def handle_post_battle(ctx: ScriptContext) -> None:
    ctx.log("等待战斗后事件...")
    for i in range(100):
        if ctx.search_label("FRLG技能替换", 95) or ctx.search_label("FRLG技能替换v2", 95):
            ctx.press("B")
            sleep(1.0)
        elif ctx.search_label("FRLG放弃学习技能", 95) or ctx.search_label("FRLG放弃学习技能v2", 95):
            ctx.press("A")
            sleep(1.0)
        elif ctx.search_label("FRLG战斗结算", 95):
            ctx.press("B")
            sleep(0.5)
        elif ctx.search_label("FRLG升级", 95):
            ctx.press("B")
            sleep(0.5)
        elif ctx.search_label("FRLG升级能力值", 95):
            ctx.press("B")
            sleep(0.5)
        elif ctx.search_label("FRLG进化What", 95):
            ctx.press("B")
            sleep(0.5)
        elif in_wild(ctx):
            return
        else:
            if i > 30:
                ctx.log("未知画面")
                frame = ctx.get_frame()
                if frame is not None:
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    os.makedirs("debug_label", exist_ok=True)
                    cv2.imencode(".png", frame)[1].tofile(f"debug_label/{ts}_unknown.png")
            ctx.press("B")
            sleep(0.5)


def defeat_pokemon(ctx: ScriptContext) -> bool:
    ctx.log("击败宝可梦...")
    pp_switches = 0

    for _ in range(10):
        sleep(0.3)
        if ctx.search_label("FRLG野怪血条", 90):
            break

    while True:
        if ctx.search_label("FRLG空PP", 98):
            if pp_switches == 0:
                ctx.log(f"一技能PP耗尽, 切换三技能")
                ctx.press("DOWN")
                sleep(1.0)
                pp_switches += 1
                continue
            elif pp_switches == 1:
                ctx.log(f"三技能PP耗尽, 切换四技能")
                ctx.press("RIGHT")
                sleep(1.0)
                pp_switches += 1
                continue
            elif pp_switches == 2:
                ctx.log(f"四技能PP耗尽, 切换二技能")
                ctx.press("UP")
                sleep(1.0)
                pp_switches += 1
                continue
            else:
                ctx.log("所有技能PP耗尽!")
                return False
        
        if ctx.search_label("FRLG首发晕厥", 95):
            for _ in range(5):
                ctx.press("B")
                sleep(0.5)
            ctx.press("DOWN")
            sleep(0.8)
            ctx.press("A")
            sleep(0.8)
            ctx.press("A")
            sleep(0.8)

        ctx.press("A")
        sleep(0.5)

        if (ctx.search_label("FRLG战斗结算", 95)
                or ctx.search_label("FRLG升级", 95)
                or in_wild(ctx)):
            sleep(1.0)
            return True


def ev_train(config: EVTrainConfig) -> None:
    def main(ctx: ScriptContext) -> None:
        targets, all_species, stat_keys = resolve_target_species(config)

        ctx.log(f"地点: {config.location} | 方式: {config.category}")
        ctx.log(f"目标努力值: [{', '.join(_STAT_ZH[k] for k in stat_keys)}]")
        ctx.log(f"目标宝可梦: {', '.join(f'{get_name(s)}(#{s}, {format_ev(get_bp(s), stat_keys)})' for s in targets)}")

        preload_sprites(all_species)

        battle_count = 0
        encounter_count = 0
        ev_totals = {k: 0 for k in stat_keys}

        while ctx.is_running():
            encounter_count += 1
            ctx.log(f"========== 第 {encounter_count} 次遇敌 ==========")

            if not use_sweet_scent(ctx):
                ctx.log("甜甜香气使用失败, 重试...")
                sleep(2.0)
                continue

            frame = ctx.get_frame()
            if frame is None:
                ctx.log("采集卡未就绪")
                break

            species_id, score, is_shiny, _, _ = identify_pokemon(frame, candidates=all_species, threshold=0.0)

            bp = get_bp(species_id)
            name = get_name(species_id) if species_id else "?"
            prefix = f"{name} ({'闪光' if is_shiny else '普通'}, 匹配度={score:.3f}, {format_ev(bp)})"

            if is_shiny:
                ctx.log(f"{prefix} -> 停止")
                ctx.press("CAPTURE", 3000)
                break

            if species_id is not None and score >= 0.95 and species_id in targets:
                ctx.log(f"{prefix} -> 击败")
                if not defeat_pokemon(ctx):
                    ctx.log("击败失败, 脚本停止")
                    break
                handle_post_battle(ctx)
                battle_count += 1
                for k in stat_keys:
                    ev_totals[k] += bp.get(k, 0)
                totals_str = " ".join(f"{_STAT_ZH[k]}:{ev_totals[k]}" for k in stat_keys)
                ctx.log(f"已刷 {battle_count} 场, 累计: {totals_str}")
            else:
                ctx.log(f"{prefix} -> 逃跑")
                run_away(ctx)
                handle_post_battle(ctx)

        ctx.log(f"脚本结束。共遇敌 {encounter_count} 次, 击败 {battle_count} 只目标宝可梦, "
                f"累计: {' '.join(f'{_STAT_ZH[k]}:{ev_totals[k]}' for k in stat_keys)}")
        ctx.press("CAPTURE", 3000)

    run_script(main)


if __name__ == "__main__":
    cfg = EVTrainConfig(
        location="Route 15",
        category="Grass",
        base_points=["speed", "sp_atk"],
    )
    ev_train(cfg)

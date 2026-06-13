# -*- coding: utf-8 -*-
import sys
import os
import cv2
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from typing import List, Optional

from easycon.context import ScriptContext
from easycon.controller import sleep
from gui import run_script
from rng.tenlines_utils import get_encounter
from assets.game_text import STAT_ZH_MAP, ALL_STATS
from assets.basepoints import BASEPOINTS

# heal center -> wild grass 路线图
heal2grass_route_map = {
    "Route 1": [
        ("walk", [("LEFT", 4), ("DOWN", 15), ("RIGHT", 6), ("DOWN", 4)])
    ],
    "Route 10": [
        ("walk", [("RIGHT", 3), ("UP", 11)]),
    ],
    "Route 22": [
        ("walk", [("LEFT", 6), ("UP", 8), ("LEFT", 10), ("LEFT", 16),
                  ("DOWN", 5), ("LEFT", 3), ("UP", 1)]),
    ],
    "Pokemon Tower 3F": [
        ("walk", [("RIGHT", 6), ("DOWN", 1), ("RIGHT", 6), ("UP", 1)]),
        ("wait", [("UP", 3)]),
        ("walk", [("UP", 9), ("RIGHT", 8)]),
        ("wait", [("LEFT", 1)]),
        ("walk", [("UP", 4), ("LEFT", 14), ("DOWN", 4), ("LEFT", 1)]),
        ("wait", [("RIGHT", 1)]),
    ]
}


def get_bp(sid):
    return BASEPOINTS.get(str(sid), {})


def get_name(sid):
    bp = get_bp(sid)
    return bp.get("zh_name", f"#{sid}")


def format_ev(bp, stat_keys=None):
    keys = stat_keys if stat_keys is not None else ALL_STATS
    return ", ".join(f"{STAT_ZH_MAP[k]}+{bp.get(k, 0)}" for k in keys if bp.get(k, 0) > 0)


@dataclass
class TrainingConfig:
    location: str = "Route 1"
    stat1: str = "speed"
    stat2: Optional[str] = None  # None 或 "(空)" 表示只训练 stat1

    def __post_init__(self):
        if self.stat2 is None or self.stat2 == "(空)":
            self.stat2 = None


def resolve_target_species(config: TrainingConfig):
    """解析目标宝可梦"""
    stat_keys = []
    for bp_item in [config.stat1]:
        if bp_item and bp_item != "(空)":
            k = bp_item.lower()
            if k not in ALL_STATS:
                raise ValueError(f"未知的基础点数类型: {bp_item}，支持: {'/'.join(ALL_STATS)}")
            stat_keys.append(k)
    if config.stat2 and config.stat2 != "(空)":
        k = config.stat2.lower()
        if k not in ALL_STATS:
            raise ValueError(f"未知的基础点数类型: {config.stat2}，支持: {'/'.join(ALL_STATS)}")
        if k not in stat_keys:
            stat_keys.append(k)

    encounter = get_encounter(config.location, "Grass", "fr_nx")
    if encounter is None:
        raise RuntimeError(
            f"未找到遇敌数据: location={config.location}, category=Grass"
        )

    encounter_species = {slot["species"] for slot in encounter.get("slots", []) if "species" in slot}
    stat_set = set(stat_keys) if stat_keys else set()

    targets = []
    for sid in sorted(encounter_species):
        bp = get_bp(sid)
        pkm_stats = {k for k in ALL_STATS if bp.get(k, 0) > 0}
        if pkm_stats and stat_set and pkm_stats.issubset(stat_set):
            targets.append(sid)
        elif not stat_set:
            # 没有指定 stat 时，所有宝可梦都是目标
            targets.append(sid)

    if not targets:
        lines = "\n".join(
            f"  {get_name(sid)} (#{sid}) → {format_ev(get_bp(sid))}"
            for sid in sorted(encounter_species)
        )
        raise RuntimeError(
            f"在 {config.location}/Grass 中没有找到"
            f"基础点数是 [{', '.join(STAT_ZH_MAP[k] for k in stat_keys)}] 子集的宝可梦！\n"
            f"该地区存在的宝可梦及基础点数:\n{lines}"
        )

    return targets, sorted(encounter_species), stat_keys


def get_location_basepoints(location: str) -> List[str]:
    """获取指定地点的草地宝可梦的所有基础点数类型"""
    encounter = get_encounter(location, "Grass", "fr_nx")
    if encounter is None:
        return []
    encounter_species = {slot["species"] for slot in encounter.get("slots", []) if "species" in slot}
    basepoints_set = set()
    for sid in encounter_species:
        bp = get_bp(sid)
        for stat in ALL_STATS:
            if bp.get(stat, 0) > 0:
                basepoints_set.add(stat)
    return sorted(basepoints_set, key=lambda x: ALL_STATS.index(x))


def handle_post_battle(ctx: ScriptContext) -> None:
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
            sleep(0.5)
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


def search_and_take_meowth_items(ctx: ScriptContext, item_counts: dict) -> None:
    pickup_total = sum(item_counts.values())
    for _ in range(3):
        if not ctx.search_label("FRLG喵喵携带物", 95):
            continue
        for __ in range(7):
            ctx.press("DOWN")
            sleep(0.5)
            for ___ in range(3):
                if ctx.search_label("FRLG喵喵携带物选中", 95):
                    break
            else:
                continue
            ctx.press("A")
            sleep(0.5)
            ctx.press("UP")
            sleep(0.5)
            ctx.press("UP")
            sleep(0.5)
            ctx.press("A")
            sleep(0.5)
            ctx.press("DOWN")
            sleep(0.5)
            ctx.press("A")
            sleep(2.0)
            text = ctx.ocr("TAKEN_ITEM").get("text") if ctx.vlm_available() else None
            if text:
                item_name = text.strip()
                item_counts[item_name] = item_counts.get(item_name, 0) + 1
                pickup_total += 1
                ctx.log(f"拾取道具: {item_name}")
                if pickup_total % 5 == 0:
                    sorted_items = sorted(item_counts.items(), key=lambda x: x[1])
                    lines = ["喵喵累计拾取:"]
                    for name, cnt in sorted_items:
                        lines.append(f"  {name}: {cnt}")
                    ctx.log("\n".join(lines))
            else:
                ctx.log("拾取道具: (识别失败)")
            sleep(0.5)
            ctx.press("B")
            sleep(1.0)


def use_sweet_scent(ctx: ScriptContext, item_counts: dict) -> bool:
    """使用甜甜香气触发遇敌"""
    open_pokemon_menu(ctx)
    sleep(2.0)

    search_and_take_meowth_items(ctx, item_counts)

    ctx.press("UP")
    sleep(0.5)
    ctx.press("UP")
    sleep(0.5)
    ctx.press("A")
    sleep(1.0)
    for _ in range(10):
        if ctx.search_label("FRLG关键词SweetScent", 95):
            break
        else:
            ctx.press("DOWN")
            sleep(0.5)
    else:
        ctx.log("队末宝可梦未找到甜甜香气 -> 递归重试")
        for _ in range(10):
            ctx.press("B")
            sleep(0.5)
        return use_sweet_scent(ctx, item_counts)

    ctx.press("A")
    sleep(8.0)

    for _ in range(10):
        sleep(0.5)
        if ctx.search_label("FRLG野怪血条", 90):
            return True
    ctx.log("甜甜香气未触发遇敌")
    return False


def defeat_pokemon(ctx: ScriptContext) -> bool:
    """击败宝可梦，PP耗尽自动切换技能"""
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
                ctx.log(f"四技能PP耗尽, 逃跑")
                return False
            else:
                raise ValueError

        if ctx.search_label("FRLG首发晕厥", 80):
            ctx.log("首发宝可梦昏厥, 替换并逃跑")
            sleep(0.5)
            ctx.press("LEFT")
            sleep(1.0)
            ctx.press("UP")
            sleep(1.0)
            ctx.press("UP")
            sleep(1.0)
            ctx.press("A")
            sleep(2.0)
            return False

        ctx.press("A")
        sleep(0.5)

        if (ctx.search_label("FRLG战斗结算", 95)
                or ctx.search_label("FRLG升级", 95)
                or in_wild(ctx)):
            sleep(1.0)
            return True


def heal_pokemon(ctx: ScriptContext) -> str:
    ctx.press("UP", duration_ms=4000)
    sleep(0.5)
    ctx.press("A")
    sleep(2.0)
    ctx.press("A")
    sleep(2.5)
    ctx.press("A")
    sleep(10.0)
    ctx.press("B")
    sleep(4.0)
    ctx.press("B")
    sleep(1.0)
    ctx.press("DOWN", duration_ms=2000)
    sleep(2.0)
    return "DOWN"


def heal_and_return(ctx: ScriptContext, config: TrainingConfig, current_direction: str) -> str:
    route_map_to_grass = heal2grass_route_map[config.location]
    route_map_to_heal = reverse_route_map(route_map_to_grass)
    current_direction = navigate(ctx=ctx, route_map=route_map_to_heal,
                                 current_direction=current_direction)
    current_direction = heal_pokemon(ctx)
    current_direction = navigate(ctx=ctx, route_map=route_map_to_grass,
                                 current_direction=current_direction)
    return current_direction


def training_loop(config: TrainingConfig) -> None:
    def main(ctx: ScriptContext) -> None:
        targets, all_species, stat_keys = resolve_target_species(config)

        ctx.log(f"地点: {config.location}")
        if config.stat2:
            ctx.log(f"目标努力值: [{STAT_ZH_MAP.get(config.stat1, config.stat1)}, {STAT_ZH_MAP.get(config.stat2, config.stat2)}]")
        else:
            ctx.log(f"目标努力值: [{STAT_ZH_MAP.get(config.stat1, config.stat1)}]")
        ctx.log(f"目标宝可梦: {', '.join(f'{get_name(s)}(#{s}, {format_ev(get_bp(s), stat_keys)})' for s in targets)}")

        preload_sprites(all_species)

        battle_count = 0
        encounter_count = 0
        ev_totals = {k: 0 for k in stat_keys}
        current_direction = "DOWN"
        item_counts = {}

        # 初始导航：从 heal center 到 grass
        route_to_grass = heal2grass_route_map.get(config.location, [])
        current_direction = navigate(ctx, route_to_grass, current_direction=current_direction)

        try:
            while ctx.is_running():
                encounter_count += 1
                ctx.log(f"========== 第 {encounter_count} 次遇敌 ==========")

                if not use_sweet_scent(ctx, item_counts):
                    ctx.log("甜甜香气使用失败, 重试...")
                    sleep(2.0)
                    if in_wild(ctx):
                        heal_and_return(ctx, config, current_direction)
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
                        ctx.log("击败失败 -> 逃跑")
                        run_away(ctx)
                        if in_wild(ctx):
                            ctx.log("逃跑成功 -> 治愈并返回")
                            heal_and_return(ctx, config, current_direction)
                            continue
                        else:
                            ctx.log("逃跑失败 -> 停止")
                            break
                    else:
                        handle_post_battle(ctx)
                    battle_count += 1
                    for k in stat_keys:
                        ev_totals[k] += bp.get(k, 0)
                    totals_str = " ".join(f"{STAT_ZH_MAP[k]}:{ev_totals[k]}" for k in stat_keys)
                    ctx.log(f"已刷 {battle_count} 场, 累计: {totals_str}")
                else:
                    ctx.log(f"{prefix} -> 逃跑")
                    run_away(ctx)
                    handle_post_battle(ctx)

        finally:
            ctx.log(f"脚本结束。共遇敌 {encounter_count} 次, 击败 {battle_count} 只目标宝可梦, "
                    f"累计: {' '.join(f'{STAT_ZH_MAP[k]}:{ev_totals[k]}' for k in stat_keys)}")

    run_script(main)


if __name__ == "__main__":
    cfg = TrainingConfig(
        location="Route 22",
        stat1="attack",
        stat2="speed",
    )
    training_loop(cfg)

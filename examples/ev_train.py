# -*- coding: utf-8 -*-
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass

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

_STAT_KEY_MAP = {
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


@dataclass
class EVTrainConfig:
    location: str = "Route 1"
    category: str = "Grass"
    base_points: str = "speed"
    game_version: str = "frlg"


def resolve_target_species(config: EVTrainConfig):
    stat_key = _STAT_KEY_MAP.get(config.base_points.lower())

    if stat_key is None:
        valid = list(set(_STAT_KEY_MAP.values()))
        raise ValueError(
            f"未知的基础点数类型: {config.base_points}，支持: HP/攻击/防御/特攻/特防/速度"
        )

    encounter = get_encounter(config.location, config.category)
    if encounter is None:
        raise RuntimeError(
            f"未找到遇敌数据: location={config.location}, category={config.category}\n"
            f"支持的 category: Grass / Surfing / OldRod / GoodRod / SuperRod"
        )

    encounter_species = set()
    for slot in encounter.get("slots", []):
        sid = slot.get("species")
        if sid is not None:
            encounter_species.add(sid)

    target = []
    for sid in sorted(encounter_species):
        sid_str = str(sid)
        bp = _BASEPOINTS.get(sid_str)
        if bp and bp[stat_key] > 0:
            target.append(sid)

    if not target:
        names_in_area = []
        for sid in sorted(encounter_species):
            sid_str = str(sid)
            bp = _BASEPOINTS.get(sid_str)
            zh = bp["zh_name"] if bp else f"#{sid}"
            ev_str = ", ".join(
                f"{_STAT_ZH[k]}+{bp[k]}" for k in ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]
                if bp and bp[k] > 0
            ) if bp else "无数据"
            names_in_area.append(f"  {zh} (#{sid}) → {ev_str}")

        area_list = "\n".join(names_in_area) if names_in_area else "(无)"
        raise RuntimeError(
            f"在 {config.location}/{config.category} 中没有找到提供 {_STAT_ZH[stat_key]} 基础点数的宝可梦！\n"
            f"该地区存在的宝可梦及基础点数:\n{area_list}"
        )

    return target, stat_key


def _navigate_to_sweet_scent(ctx: ScriptContext) -> bool:
    ctx.press("X")
    sleep(1.0)

    for _ in range(10):
        if ctx.search_label("3代关键词POKeMON选中", 90):
            break
        ctx.press("DOWN")
        sleep(0.5)
    else:
        ctx.log("无法定位到POKeMON菜单")
        return False

    ctx.press("A")
    sleep(2.0)
    ctx.press("A")
    sleep(1.5)

    for _ in range(5):
        if ctx.search_label("3代关键词Skills", 90):
            break
        ctx.press("DOWN")
        sleep(0.5)
    else:
        ctx.log("无法定位到技能菜单")
        return False

    ctx.press("A")
    sleep(1.0)
    ctx.press("A")
    return True


def use_sweet_scent(ctx: ScriptContext) -> bool:
    ctx.log("使用甜甜香气...")

    if not _navigate_to_sweet_scent(ctx):
        return False

    for _ in range(60):
        sleep(0.5)
        if ctx.search_label("3代野怪血条", 90):
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
        if ctx.search_label("3代逃跑", 90):
            ctx.press("A")
            sleep(1.0)
            break

    for _ in range(30):
        sleep(0.5)
        if ctx.search_label("3代家门草丛", 90):
            return
        ctx.press("B")
        sleep(0.3)


def _cancel_evolution(ctx: ScriptContext) -> None:
    ctx.log("取消进化...")
    for _ in range(50):
        ctx.press("B")
        sleep(0.2)
        if ctx.search_label("3代升级能力值", 95):
            return
        if ctx.search_label("3代技能替换", 95):
            return
        if ctx.search_label("3代战斗结算", 95):
            return
        if ctx.search_label("3代家门草丛", 90):
            return
    ctx.log("进化取消循环结束")


def _refuse_skill_learning(ctx: ScriptContext) -> None:
    for _ in range(60):
        if ctx.search_label("3代技能替换", 95):
            break
        if ctx.search_label("3代放弃学习技能", 95):
            break
        if ctx.search_label("3代战斗结算", 95):
            return
        if ctx.search_label("3代家门草丛", 90):
            return
        if ctx.search_label("3代升级能力值", 95):
            return
        sleep(0.3)
    else:
        return

    ctx.log("放弃学习新技能...")
    ctx.press("DOWN")
    sleep(0.3)
    ctx.press("A")
    sleep(1.0)

    for _ in range(30):
        if ctx.search_label("3代放弃学习技能", 95):
            ctx.press("A")
            sleep(1.0)
            break
        sleep(0.3)
    ctx.log("已跳过新技能学习")


def _handle_post_battle_events(ctx: ScriptContext) -> None:
    ctx.log("等待战斗后事件...")
    for _ in range(100):
        if ctx.search_label("3代升级", 95):
            ctx.log("检测到升级")
            sleep(1.0)

        if ctx.search_label("3代升级能力值", 95):
            ctx.log("能力值变化")
            sleep(0.5)

        if ctx.search_label("3代技能替换", 95):
            _refuse_skill_learning(ctx)
            continue

        if ctx.search_label("3代放弃学习技能", 95):
            ctx.press("A")
            sleep(1.0)
            continue

        if ctx.search_label("3代战斗结算", 95):
            sleep(0.5)
            continue

        if ctx.search_label("3代家门草丛", 90):
            return
        if ctx.search_label("3代对话", 90):
            return
        if ctx.search_label("3代水面", 90):
            return
        if ctx.search_label("3代洞穴", 90):
            return

        ctx.press("B")
        sleep(0.3)


def defeat_pokemon(ctx: ScriptContext) -> bool:
    ctx.log("击败宝可梦...")
    pp_switches = 0
    max_pp_switches = 5

    for _ in range(10):
        sleep(0.3)
        if ctx.search_label("3代野怪血条", 90):
            break

    while True:
        ctx.press("A")
        sleep(0.3)

        if ctx.search_label("3代战斗结算", 95):
            sleep(2.0)
            return True
        if ctx.search_label("3代升级", 95):
            sleep(2.0)
            return True
        if ctx.search_label("3代空PP", 98):
            if pp_switches < max_pp_switches:
                ctx.log(f"PP耗尽, 切换技能 ({pp_switches + 1}/{max_pp_switches})")
                ctx.press("DOWN")
                sleep(0.3)
                pp_switches += 1
            else:
                ctx.log("所有技能PP耗尽!")
                return False


def dismiss_battle_end(ctx: ScriptContext) -> None:
    _handle_post_battle_events(ctx)


def ev_train(config: EVTrainConfig) -> None:
    def main(ctx: ScriptContext) -> None:
        target_ids, stat_key = resolve_target_species(config)

        species_names = []
        for sid in target_ids:
            sid_str = str(sid)
            bp = _BASEPOINTS.get(sid_str, {})
            zh = bp.get("zh_name", f"#{sid}")
            ev = bp.get(stat_key, 0)
            species_names.append(f"{zh}(#{sid}, {_STAT_ZH[stat_key]}+{ev})")

        ctx.log(f"地点: {config.location} | 方式: {config.category}")
        ctx.log(f"目标努力值: {_STAT_ZH[stat_key]}")
        ctx.log(f"目标宝可梦: {', '.join(species_names)}")
        ctx.log(f"目标物种ID: {target_ids}")

        preload_sprites(target_ids)

        battle_count = 0
        ev_total = 0

        while ctx.is_running():
            ctx.log(f"========== 第 {battle_count + 1} 次遇敌 ==========")

            if not use_sweet_scent(ctx):
                ctx.log("甜甜香气使用失败, 重试...")
                sleep(2.0)
                continue

            frame = ctx.get_frame()
            if frame is None:
                ctx.log("采集卡未就绪")
                run_away(ctx)
                dismiss_battle_end(ctx)
                continue

            species_id, score, is_shiny, _fx, _fy = identify_pokemon(
                frame, candidates=target_ids, threshold=0.0
            )

            if is_shiny:
                ctx.log("★★★ 闪光宝可梦出现! 脚本停止 ★★★")
                ctx.press("CAPTURE", 3000)
                break

            if species_id is not None and score >= 0.95:
                sid_str = str(species_id)
                bp = _BASEPOINTS.get(sid_str, {})
                zh = bp.get("zh_name", f"#{species_id}")
                ev = bp.get(stat_key, 0)
                ctx.log(f"目标: {zh} (匹配度={score:.3f}, {_STAT_ZH[stat_key]}+{ev})")

                if not defeat_pokemon(ctx):
                    ctx.log("击败失败, 脚本停止")
                    break

                dismiss_battle_end(ctx)

                battle_count += 1
                ev_total += ev
                ctx.log(
                    f"已刷 {battle_count} 场, "
                    f"累计{_STAT_ZH[stat_key]}努力值: {ev_total}"
                )

                ctx.press("CAPTURE", 1000)
            else:
                sid_str = str(species_id) if species_id else "?"
                ctx.log(f"非目标 (species={sid_str}, score={score:.3f}), 逃跑")
                run_away(ctx)
                dismiss_battle_end(ctx)

        ctx.log(
            f"脚本结束。共击败 {battle_count} 只目标宝可梦, "
            f"累计{_STAT_ZH[stat_key]}努力值: {ev_total}"
        )
        ctx.press("CAPTURE", 3000)

    run_script(main)


if __name__ == "__main__":
    cfg = EVTrainConfig(
        location="Route 1",
        category="Grass",
        base_points="speed",
    )
    ev_train(cfg)

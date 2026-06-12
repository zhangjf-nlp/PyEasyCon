import os
import time as _time
from typing import Any, Optional, Tuple

import cv2
import numpy as np

from easycon.context import ScriptContext
from easycon.controller import sleep
from rng.config import RNGConfig, SessionState
from script_utils.navigation import in_wild
from vision.sprite import identify_pokemon, detect_gba_area, SPRITE_NATIVE
from rng.tenlines_utils import get_species_en_name, get_species_id, get_species_zh_name, get_encounter_species_list


def check_shiny(
    ctx: ScriptContext,
    cfg: RNGConfig,
    state: Optional[SessionState] = None,
    attempt: int = 0,
) -> Tuple[bool, Optional[str]]:
    ctx.log("识别宝可梦...")

    for _ in range(30):
        if ctx.search_label("FRLG野怪血条", 90):
            break
        else:
            ctx.press("B")
        sleep(0.5)
    else:
        ctx.log("画面异常")
        frame = ctx.get_frame()
        if frame is not None:
            ts = _time.strftime("%Y%m%d_%H%M%S")
            os.makedirs("debug_label", exist_ok=True)
            cv2.imencode(".png", frame)[1].tofile(f"debug_label/{ts}_abnormal.png")
        return False, None

    if cfg.rng_method in ["Static 1", "Static 4"]:
        candidates = [get_species_id(cfg.pokemon_species)]
    else:
        candidates = get_encounter_species_list(cfg.rng_location, cfg.rng_category, cfg.game_version)
    if not candidates:
        raise RuntimeError(f"Empty encounter list for {cfg.rng_location}/{cfg.rng_category}")

    frame = ctx.get_frame()
    if frame is None:
        raise RuntimeError("采集卡未就绪")

    species_id, score, is_shiny, fx_match, fy_match = identify_pokemon(
        frame, candidates=candidates, threshold=0.0
    )

    gx, gy, scale = detect_gba_area(frame)
    spx = int(SPRITE_NATIVE * scale)
    sx_roi = gx + int(140 * scale)
    sy_roi = gy
    sw_roi = int(72 * scale)
    sh_roi = int(100 * scale)

    if species_id is None or score < 0.90:
        ts = _time.strftime("%Y%m%d_%H%M%S")
        os.makedirs("debug_label", exist_ok=True)
        cv2.imencode(".png", frame)[1].tofile(f"debug_label/{ts}.png")
        ctx.log(f"识别失败 (score={score:.3f})")
        raise RuntimeError(f"宝可梦识别失败 (最高匹配度={score:.3f})")

    pkm_en = get_species_en_name(get_species_zh_name(species_id))
    ctx.log(
        f'match: {pkm_en} (#{species_id} {"shiny" if is_shiny else "normal"}) score={score:.3f}'
    )

    if state is not None and state.log_dir is not None:
        ctx.save_ocr_screenshot(
            f"{state.log_dir}/screens/{attempt:03d}-APPEARED.png", "APPEARED"
        )

    dbg = frame.copy()
    cv2.rectangle(dbg, (sx_roi, sy_roi), (sx_roi + sw_roi, sy_roi + sh_roi), (255, 255, 0), 2)
    cv2.rectangle(dbg, (fx_match, fy_match), (fx_match + spx, fy_match + spx), (0, 255, 0), 3)
    cv2.putText(
        dbg, f"{pkm_en} score={score:.3f}", (sx_roi, sy_roi - 5),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1,
    )
    os.makedirs("debug_label", exist_ok=True)
    safe_name = pkm_en.replace(" ", "_").replace("'", "")
    cv2.imencode(".png", dbg)[1].tofile(f"debug_label/{safe_name}.png")

    return is_shiny, pkm_en


def catch_with_ball(ctx: ScriptContext) -> bool:
    ctx.log("尝试捕获...")
    for _ in range(30):
        ctx.press("B")
        sleep(0.5)
        ctx.press("RIGHT")
        sleep(0.5)
        ctx.press("UP")
        sleep(0.5)
        if ctx.search_label("FRLG关键词Bag", 90):
            break
    else:
        ctx.log("无法打开背包")
        return False

    for i in range(50):
        sleep(2.0)
        ctx.press("A")
        for _ in range(5):
            ctx.press("RIGHT")
            sleep(0.5)
            if ctx.search_label("FRLG关键词PokeBalls", 95):
                break
        sleep(0.5)
        ball = None
        if ctx.search_label("FRLG关键词MasterBall", 90):
            ball = "大师球"
        elif ctx.search_label("FRLG关键词UltraBall", 90):
            ball = "高级球"
        elif ctx.search_label("FRLG关键词GreatBall", 90):
            ball = "超级球"
        elif ctx.search_label("FRLG关键词POKeBall", 90):
            ball = "精灵球"
        else:
            raise ValueError("未找到可用精灵球")
        for _ in range(20):
            if ctx.search_label(f"FRLG选中{ball}", 95):
                break
            ctx.press("DOWN" if _ < 10 else "UP")
            sleep(1.0)
        for _ in range(10):
            ctx.press("A")
            sleep(1.0)
            if ctx.search_label("FRLG野怪血条", 90):
                break
        else:
            ctx.log("血条异常退出")
            return False
        for _ in range(60):
            ctx.press("B")
            sleep(1.0)
            if ctx.search_label("FRLG关键词Bag", 90):
                break
            if ctx.search_label("FRLG关键词Gotcha", 80):
                return True
        else:
            ctx.log("界面异常退出")
            return False
    return False


def catch_with_safari_strategy(ctx: ScriptContext, pokemon_en: str):
    ctx.log(f"尝试捕获{pokemon_en}...")
    for _ in range(30):
        ctx.press("B")
        sleep(0.5)
        if ctx.search_label("FRLG狩猎区选中Ball", 80):
            break
    
    if pokemon_en in ["Chansey", "Kangaskhan", "Dragonair", "Pinsir", "Scyther", "Tauros"]:
        strategy = "🍯🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️⚾️🪨⚾️"
    elif pokemon_en in ["Dratini"]:
        strategy = "🍯🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️⚾️🪨⚾️"
    elif pokemon_en in ["Seaking", "Parasect", "Venomoth"]:
        strategy = "🍯🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️🍯⚾️⚾️⚾️🍯⚾️⚾️🪨⚾️⚾️"
    elif pokemon_en in ["Exeggcute", "Nidorino", "Nidorina", "Rhyhorn"]:
        strategy = "⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️🪨⚾️⚾️"
    elif pokemon_en in ["Psyduck", "Slowpoke", "Paras", "Venonat", "Doduo"]:
        strategy = "⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️🪨⚾️"
    elif pokemon_en in ["Magikarp", "Goldeen", "Nidoran♀", "Nidoran♂", "Poliwag"]:
        strategy = "⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️⚾️"
    else:
        raise NotImplementedError(pokemon_en)
    
    ctx.log(f"捕获策略：{strategy}")
    while len(strategy) > 0:
        for action, (button_a, button_b, label) in {
            "⚾️": ("UP", "LEFT", "FRLG狩猎区选中Ball"),
            "🍯": ("UP", "RIGHT", "FRLG狩猎区选中Bait"),
            "🪨": ("DOWN", "LEFT", "FRLG狩猎区选中Rock"),
        }.items():
            if strategy.startswith(action):
                strategy = strategy[len(action):]
                break
        else:
            raise ValueError(f"Failed to parse the remaining strategy: {strategy}")
        for _ in range(30):
            ctx.press("B")
            sleep(0.3)
            ctx.press(button_a)
            sleep(0.3)
            ctx.press(button_b)
            sleep(0.3)
            if ctx.search_label(label, 80):
                break
        else:
            ctx.log("异常画面退出")
            return False
        
        sleep(0.3)
        ctx.press("A")
        for _ in range(5):
            sleep(1.0)
            if not ctx.search_label(label, 80):
                break
        
        for _ in range(30):
            sleep(1.0)
            if ctx.search_label("FRLG关键词Gotcha", 80):
                return True
            if in_wild(ctx):
                return False
            if ctx.search_label(label, 80):
                break
        else:
            ctx.log("异常画面")
            return False
    
    return False


def open_pokemon_menu(ctx: ScriptContext) -> None:
    for _ in range(20):
        ctx.press("B")
        sleep(0.5)
        ctx.press("B")
        sleep(0.5)
        ctx.press("X")
        sleep(1.0)
        if ctx.search_label("FRLG菜单", 90):
            break
    else:
        ctx.log(f"[观察失败警告] 未能打开菜单")
    for _ in range(10):
        sleep(1.5)
        if ctx.search_label("FRLG菜单选中POKeMON", 98):
            break
        elif ctx.search_label("FRLG关键词BAG选中", 90):
            ctx.press("UP")
            break
        else:
            ctx.press("DOWN")
    else:
        ctx.log(f"[观察失败警告] 未能找到背包")
    sleep(1.0)
    ctx.press("A")


def check_last_pokemon(ctx: ScriptContext) -> None:
    ctx.log("查看末位精灵...")
    open_pokemon_menu(ctx)
    sleep(2.0)
    ctx.press("UP")
    sleep(1.0)
    ctx.press("UP")
    sleep(1.0)
    for _ in range(10):
        ctx.press("A")
        sleep(1.0)
        if ctx.search_label("FRLG精灵球", 85):
            break

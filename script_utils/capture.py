import os
import time as _time
from typing import Any, Optional, Tuple

import cv2
import numpy as np

from easycon.context import ScriptContext
from rng.config import RNGConfig, SessionState
from vision.sprite import identify_pokemon as _identify, detect_gba_area, SPRITE_NATIVE
from rng.tenlines_utils import get_species_en_name, get_species_zh_name, get_encounter_species_list
from script_utils.hit import sleep


def check_shiny(
    ctx: ScriptContext,
    cfg: RNGConfig,
    state: Optional[SessionState] = None,
    attempt: int = 0,
) -> Tuple[bool, Optional[str]]:
    ctx.log("识别宝可梦...")

    for _ in range(20):
        if ctx.search_label("3代野怪血条", 90):
            break
        sleep(0.5)
    else:
        return False, None

    candidates = get_encounter_species_list(cfg.rng_location, cfg.rng_category)
    if not candidates:
        raise RuntimeError(f"Empty encounter list for {cfg.rng_location}/{cfg.rng_category}")

    frame = ctx.get_frame()
    if frame is None:
        raise RuntimeError("采集卡未就绪")

    species_id, score, is_shiny, fx_match, fy_match = _identify(
        frame, candidates=candidates, threshold=0.0
    )

    gx, gy, scale = detect_gba_area(frame)
    spx = int(SPRITE_NATIVE * scale)
    sx_roi = gx + int(140 * scale)
    sy_roi = gy
    sw_roi = int(72 * scale)
    sh_roi = int(100 * scale)

    if species_id is None or score < 0.95:
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
        if ctx.search_label("3代关键词Bag", 90):
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
            if ctx.search_label("3代关键词PokeBalls", 95):
                break
        for _ in range(5):
            if ctx.search_label("3代关键词UltraBall选中", 98):
                break
            ctx.press("DOWN")
            sleep(0.5)
        for _ in range(10):
            ctx.press("A")
            sleep(0.5)
            break
        for _ in range(10):
            ctx.press("A")
            sleep(0.5)
            if ctx.search_label("3代野怪血条", 90):
                break
        else:
            ctx.log("血条异常退出")
            return False
        for _ in range(60):
            ctx.press("B")
            sleep(1.0)
            if ctx.search_label("3代关键词Bag", 90):
                break
            if ctx.search_label("3代关键词Gotcha", 90):
                return True
        else:
            ctx.log("界面异常退出")
            return False
    return False


def check_last_pokemon(ctx: ScriptContext) -> None:
    ctx.log("查看末位精灵...")
    for _ in range(20):
        ctx.press("B")
        sleep(0.5)
        ctx.press("B")
        sleep(0.5)
        ctx.press("X")
        sleep(1.0)
        if ctx.search_label("3代关键词POKeMON", 90):
            break
    if ctx.search_label("3代关键词BAG选中", 95):
        ctx.press("UP")
        sleep(0.5)
    for _ in range(20):
        if ctx.search_label("3代关键词POKeMON选中", 97):
            break
        ctx.press("DOWN")
        sleep(0.5)
    sleep(2.0)
    ctx.press("A")
    sleep(1.8)
    ctx.press("UP")
    sleep(1.0)
    ctx.press("UP")
    sleep(1.0)
    for _ in range(100):
        ctx.press("A")
        sleep(1.0)
        if ctx.search_label("3代精灵球", 85):
            break

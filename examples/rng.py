# -*- coding: utf-8 -*-
import sys
import os
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from gui import run_script
from rng.config import RNGConfig, SessionState
from rng.tenlines_utils import calibration as calibration_api
from script_utils.hit import hit
from script_utils.capture import check_shiny, catch_with_ball, catch_with_safari_strategy, check_last_pokemon
from script_utils.session import observe_pokemon, init_log_dir, run_calibration
from script_utils.navigation import in_wild, restart


def attempt_once(ctx: ScriptContext, cfg: RNGConfig, state: Optional[SessionState] = None) -> bool:
    """单次刷闪尝试（hit → 判定 → 校准/观察），返回 True 表示找到并处理了闪光目标"""
    if state is None:
        state = SessionState()
    state.attempt_index += 1
    mode = "乱数" if cfg.advances_bias or cfg.seed_bias else "遍历"
    ctx.log(f"========== {mode}刷闪尝试第 {state.attempt_index} 次 ==========")

    hit(ctx, cfg)

    if cfg.rng_location.startswith("Safari Zone"):
        is_shiny, pokemon_en = check_shiny(ctx, cfg, state, state.attempt_index)
        if pokemon_en is None:
            return False
        if is_shiny:
            ctx.log("闪光出现!")
            ctx.press("CAPTURE", 3000)
            ctx.screen_record_start()
            if catch_with_safari_strategy(ctx, pokemon_en):
                ctx.screen_record_save()
                ctx.log("捕获成功!")
                return True
            ctx.screen_record_save()
            ctx.log("捕获失败...")
            ctx.press("CAPTURE", 3000)
            time.sleep(3.0)
            return False
        if state.fast_attempts:
            state.fast_attempts -= 1
            return False
        if catch_with_safari_strategy(ctx, pokemon_en):
            check_last_pokemon(ctx)
            observe_pokemon(ctx, state, cfg, state.attempt_index, pokemon_en)
        run_calibration(ctx, state, cfg)
        return False

    if cfg.rng_category in ["Grass", "Surfing", "SuperRod", "GoodRod", "OldRod", "RockSmash", "Stationary", "Legend", "Event"]:
        is_shiny, pokemon_en = check_shiny(ctx, cfg, state, state.attempt_index)
        if pokemon_en is None:
            return False
        if is_shiny:
            ctx.log("闪光出现!")
            return True
        if state.fast_attempts:
            state.fast_attempts -= 1
            return False
        if catch_with_ball(ctx):
            check_last_pokemon(ctx)
            observe_pokemon(ctx, state, cfg, state.attempt_index, pokemon_en)
        run_calibration(ctx, state, cfg)
        return False

    if cfg.rng_category in ["Gift", "Fossil", "GameCorner"]:
        check_last_pokemon(ctx)
        if ctx.search_label("FRLG闪光", 80):
            ctx.log("闪光出现!")
            return True
        if state.fast_attempts:
            state.fast_attempts -= 1
            return False
        observe_pokemon(ctx, state, cfg, state.attempt_index, cfg.pokemon_species)
        run_calibration(ctx, state, cfg)
        return False

    raise NotImplementedError(cfg.rng_category)


def launch(cfg: RNGConfig, state: SessionState = None, controller=None) -> None:
    state = SessionState() if state is None else state
    def main(ctx: ScriptContext) -> None:
        init_log_dir(ctx, state, cfg)

        ctx.log(f"GameSettings: {cfg.game_settings}")
        ctx.log(f"RNGTarget: {cfg.target}")
        ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
        ctx.log(
            f"Seed takes {cfg.schedule.seed_ms}ms | TV takes {cfg.schedule.advances_ms_tv}ms "
            f"| Normal takes {cfg.schedule.advances_ms_normal}ms"
        )

        if cfg.schedule.seed_ms < 35000:
            ctx.log(f'[Warning] Too low seed time: {cfg.schedule.seed_ms}ms')
        if cfg.schedule.advances_ms_tv < 1000:
            ctx.log(f'[Warning] Too low TV time: {cfg.schedule.advances_ms_tv}ms')

        ctx.log("校验目标是否为闪光...")
        target_results = calibration_api(
            game=cfg.game_version,
            tid=cfg.trainer_id,
            sid=cfg.secret_id,
            method=cfg.rng_method,
            category=cfg.rng_category,
            location=cfg.rng_location,
            pokemon=cfg.pokemon_species,
            seed=f"{cfg.target.seed_hex:04X}",
            advances=cfg.target.advances,
            settings=cfg.game_settings,
            seed_bias=0,
            advances_bias=0,
        )
        is_target_shiny = any(r.shiny not in ("", "None") for r in target_results)
        if not is_target_shiny:
            ctx.log("[Warning] 目标不是闪光! 请检查配置是否正确。继续执行...")
        else:
            ctx.log("目标确认为闪光，开始乱数。")

        if in_wild(ctx):
            restart(ctx)

        while ctx.is_running():
            if attempt_once(ctx, cfg, state):
                break
            restart(ctx)

        ctx.press("CAPTURE", 3000)

    run_script(main, controller=controller)
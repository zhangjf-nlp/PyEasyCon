# -*- coding: utf-8 -*-
import sys
import os
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from gui import run_script
from rng.config import RNGConfig, SessionState
from rng.tenlines_utils import calibration as calibration_api
from script_utils.hit import hit
from script_utils.capture import check_shiny, catch_with_ball, catch_with_safari_strategy, check_last_pokemon
from script_utils.session import observe_pokemon, init_log_dir, run_calibration, ready_for_calibration
from script_utils.navigation import in_wild, restart


def launch(cfg: RNGConfig, state: SessionState = None) -> None:
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

        state.attempt_index = 0
        while ctx.is_running():
            state.attempt_index += 1
            ctx.log(f"========== 乱数尝试第 {state.attempt_index} 次 ==========")

            hit(ctx, cfg)

            if cfg.rng_location.startswith("Safari Zone"):
                is_shiny, pokemon_en = check_shiny(ctx, cfg, state, state.attempt_index)
                if is_shiny:
                    ctx.log("闪光出现!")
                    ctx.press("CAPTURE", 3000)
                    ctx.screen_record_start()
                    if catch_with_safari_strategy(ctx, pokemon_en):
                        ctx.screen_record_save()
                        ctx.log("捕获成功!")
                        break
                    else:
                        ctx.screen_record_save()
                        ctx.log("捕获失败...")
                        ctx.press("CAPTURE", 3000)
                elif state.fast_attempts:
                    state.fast_attempts -= 1
                elif pokemon_en:
                    if catch_with_safari_strategy(ctx, pokemon_en):
                        check_last_pokemon(ctx)
                        observe_pokemon(ctx, state, cfg, state.attempt_index, pokemon_en)
                    if ready_for_calibration(state, cfg):
                        run_calibration(ctx, state, cfg)
                    
            elif cfg.rng_category in ["Grass", "Surfing", "SuperRod", "GoodRod", "OldRod", "Stationary", "Legend", "Fossil", "Event"]:
                is_shiny, pokemon_en = check_shiny(ctx, cfg, state, state.attempt_index)
                if is_shiny:
                    ctx.log("闪光出现!")
                    break
                elif state.fast_attempts:
                    state.fast_attempts -= 1
                elif pokemon_en:
                    if catch_with_ball(ctx):
                        check_last_pokemon(ctx)
                        observe_pokemon(ctx, state, cfg, state.attempt_index, pokemon_en)
                    if ready_for_calibration(state, cfg):
                        run_calibration(ctx, state, cfg)
            
            elif cfg.rng_category in ["Gift", "Game Corner"]:
                check_last_pokemon(ctx)
                if ctx.search_label("FRLG闪光", 80):
                    ctx.log("闪光出现!")
                    break
                elif state.fast_attempts:
                    state.fast_attempts -= 1
                else:
                    observe_pokemon(ctx, state, cfg, state.attempt_index, cfg.pokemon_species)
                    if ready_for_calibration(state, cfg):
                        run_calibration(ctx, state, cfg)
            
            else:
                raise NotImplementedError(cfg.rng_category)

            restart(ctx)

        ctx.press("CAPTURE", 3000)

    run_script(main)

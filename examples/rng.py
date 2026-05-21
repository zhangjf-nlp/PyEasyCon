# -*- coding: utf-8 -*-
import sys
import os
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from gui import run_script
from rng.config import RNGConfig, SessionState
from script_utils.hit import hit
from script_utils.capture import check_shiny, catch_with_ball, check_last_pokemon
from script_utils.finetune import record_for_finetune, init_log_dir, run_calibration
from script_utils.navigation import restart


def launch(cfg: RNGConfig) -> None:
    def main(ctx: ScriptContext) -> None:
        state = SessionState()
        init_log_dir(ctx, state, cfg)

        ctx.log(f"GameSettings: {cfg.game_settings}")
        ctx.log(f"Seed={cfg.seed}ms Advances={cfg.advances}")
        ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
        ctx.log(
            f"Seed takes {cfg.seed_ms}ms | TV takes {cfg.advances_ms_tv}ms "
            f"| Normal takes {cfg.advances_ms_normal}ms"
        )

        if cfg.seed_ms < 35000:
            ctx.log(f'[Warning] Too low seed time: {cfg.seed_ms}ms')
        if cfg.advances_ms_tv < 1000:
            ctx.log(f'[Warning] Too low TV time: {cfg.advances_ms_tv}ms')

        count = 0
        while ctx.is_running():
            count += 1
            ctx.log(f"========== 乱数尝试第 {count} 次 ==========")

            hit(ctx, cfg)

            if cfg.rng_category in ["Grass", "Surfing", "SuperRod"]:
                is_shiny, pokemon_en = check_shiny(ctx, cfg, state, count)
                if is_shiny:
                    ctx.log("闪光出现!")
                    break
                elif state.fast_attempts:
                    state.fast_attempts -= 1
                elif pokemon_en:
                    if catch_with_ball(ctx):
                        check_last_pokemon(ctx)
                        record_for_finetune(ctx, state, cfg, count, pokemon_en)
                    if state.valid_calibration_attempts >= cfg.finetune_per_precicase:
                        run_calibration(ctx, state, cfg)
            elif cfg.rng_category in ["Gift", "Game Corner"]:
                check_last_pokemon(ctx)
                if ctx.search_label("3代闪光", 80):
                    ctx.log("闪光出现!")
                    break
                elif state.fast_attempts:
                    state.fast_attempts -= 1
                else:
                    record_for_finetune(ctx, state, cfg, count, cfg.pokemon_species)
                    if state.valid_calibration_attempts >= cfg.finetune_per_precicase:
                        run_calibration(ctx, state, cfg)
            else:
                raise NotImplementedError(cfg.rng_category)

            restart(ctx)

        ctx.press("CAPTURE", 3000)

    run_script(main)

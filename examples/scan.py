# -*- coding: utf-8 -*-
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from gui import run_script
from rng.config import RNGConfig, RNGSchedule, RNGSlot, SessionState
from rng.tenlines_utils import GameSettings
from examples.rng import attempt_once
from script_utils.navigation import restart

SEED_MS_MIN    = 12000
SEED_MS_STEP   = 32
NORMAL_MS_MIN  = 5000
NORMAL_MS_STEP = 32

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scan_logs")

SCAN_GAME_SETTINGS = GameSettings.from_string("Mono | Help | Seed Button: A | Extra Button: None")


def launch(
    method: str,
    category: str,
    location: str,
    pokemon_species: str,
    game_version: str,
    normal_ms_min: int = NORMAL_MS_MIN,
    controller=None,
) -> None:
    rng_method = "Static 1" if method == "Static" else "Wild 1"

    def progress_path() -> str:
        progress_key = re.sub(r"[^\w]", "_", f"{game_version}_{method}_{category}_{pokemon_species}").lower()
        return os.path.join(LOGS_DIR, f"scan_progress_{progress_key}.json")

    def load_progress() -> int:
        try:
            with open(progress_path(), "r") as f:
                return int(json.load(f).get("k", 0))
        except Exception:
            return 0

    def save_progress(k: int) -> None:
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
            with open(progress_path(), "w") as f:
                json.dump({"k": k}, f)
        except Exception:
            pass

    def clear_progress() -> None:
        try:
            os.remove(progress_path())
        except Exception:
            pass

    def main(ctx: ScriptContext) -> None:
        state = SessionState(fast_attempts=65536, log_root="scan_logs")
        start_k = load_progress()
        if start_k:
            ctx.log(f"[scan] resuming from k={start_k}")
        total_done = start_k * (start_k + 1) / 2

        for k in range(start_k, 1000):
            for si in range(k + 1):
                if not ctx.is_running():
                    return
                total_done += 1
                seed_ms   = SEED_MS_MIN + si * SEED_MS_STEP
                normal_ms = normal_ms_min + (k - si) * NORMAL_MS_STEP

                cfg = RNGConfig(
                    game_version=game_version,
                    pokemon_species=pokemon_species,
                    rng_category=category,
                    rng_location=location,
                    rng_method=rng_method,
                    game_settings=SCAN_GAME_SETTINGS,
                    seed_bias=0,
                    advances_bias=0,
                )
                cfg.schedule = RNGSchedule(
                    seed_ms=seed_ms,
                    advances_ms_tv=0,
                    advances_ms_normal=normal_ms,
                )

                if attempt_once(ctx, cfg, state):
                    ctx.log(f"闪光出现！！共刷{total_done}次")
                    ctx.press("CAPTURE", 3000)
                    clear_progress()
                    return
                restart(ctx)
            
            save_progress(k)

    run_script(main, controller=controller)


if __name__ == "__main__":
    launch(
        method="Static",
        category="Fossil",
        location="Fossil",
        pokemon_species="Omanyte",
        game_version="fr_nx",
    )
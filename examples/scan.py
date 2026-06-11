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

SEED_MS_MIN    = 33000
SEED_MS_STEP   = 32
NORMAL_MS_MIN  = 10000
NORMAL_MS_STEP = 32

SCAN_RADIUS       = [100, 200, 300]
PROGRESS_INTERVAL = 10
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rng_logs")

SCAN_GAME_SETTINGS = GameSettings.from_string("Mono | Help | Seed Button: A | Extra Button: None")


def iter_grid(radius: int, prev_radius: int, skip: int = 0):
    skipped = 0
    for si in range(radius):
        for ni in range(radius):
            if si < prev_radius and ni < prev_radius:
                continue
            if skipped < skip:
                skipped += 1
                continue
            yield si, ni, SEED_MS_MIN + si * SEED_MS_STEP, NORMAL_MS_MIN + ni * NORMAL_MS_STEP


def launch(
    method: str,
    category: str,
    location: str,
    pokemon_species: str,
    game_version: str,
) -> None:
    rng_method = "Static 1" if method == "Static" else "Wild 1"

    def progress_key() -> str:
        return re.sub(r"[^\w]", "_", f"{game_version}_{method}_{category}_{pokemon_species}").lower()

    def progress_path() -> str:
        return os.path.join(LOGS_DIR, f"scan_progress_{progress_key()}.json")

    def load_progress() -> int:
        try:
            with open(progress_path(), "r") as f:
                return int(json.load(f).get("skip_iters", 0))
        except Exception:
            return 0

    def save_progress(skip_iters: int) -> None:
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
            with open(progress_path(), "w") as f:
                json.dump({"skip_iters": skip_iters, "key": progress_key()}, f)
        except Exception:
            pass

    def clear_progress() -> None:
        try:
            os.remove(progress_path())
        except Exception:
            pass

    skip_iters = load_progress()
    if skip_iters:
        print(f"[scan] resuming from skip_iters={skip_iters} (loaded from progress log)")

    def main(ctx: ScriptContext) -> None:
        attempt     = 0
        prev_radius = 0
        total_done  = 0
        state = SessionState(fast_attempts=sys.maxsize)

        for radius in SCAN_RADIUS:
            ctx.log(f"=== scan radius {radius} ===")
            first = (prev_radius == 0 and radius == SCAN_RADIUS[0])
            for si, ni, seed_ms, normal_ms in iter_grid(radius, prev_radius, skip_iters if first else 0):
                if not ctx.is_running():
                    return
                attempt    += 1
                total_done += 1
                ctx.log(f"#{attempt} seed={seed_ms}ms normal={normal_ms}ms (s{si} n{ni})")

                cfg = RNGConfig(
                    game_version=game_version,
                    pokemon_species=pokemon_species,
                    rng_category=category,
                    rng_location=location,
                    rng_method=rng_method,
                    game_settings=SCAN_GAME_SETTINGS,
                    target=RNGSlot(0x0000, seed_ms, 0),
                    seed_bias=0,
                    advances_bias=0,
                )
                cfg.schedule = RNGSchedule(
                    seed_ms=seed_ms,
                    advances_ms_tv=0,
                    advances_ms_normal=normal_ms,
                )

                state.attempt_index = 0
                state.fast_attempts = sys.maxsize
                if attempt_once(ctx, cfg, state):
                    ctx.log(f"shiny found! seed={seed_ms}ms normal={normal_ms}ms")
                    ctx.press("CAPTURE", 3000)
                    clear_progress()
                    return
                restart(ctx)

                if total_done % PROGRESS_INTERVAL == 0:
                    save_progress(skip_iters + total_done)

            prev_radius = radius

        ctx.log("scan complete, no shiny found")
        clear_progress()

    run_script(main)


if __name__ == "__main__":
    launch(
        method="Static",
        category="Fossil",
        location="Fossil",
        pokemon_species="Omanyte",
        game_version="fr_nx",
    )
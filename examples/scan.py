# -*- coding: utf-8 -*-
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext, sleep
from gui import run_script
from rng.config import RNGSchedule
from rng.tenlines_utils import GameSettings
from script_utils.hit import EXTRA_A_PRESSES, hit_init_seed, hit_A, hit_sweet_scent, hit_rod
from script_utils.capture import (
    check_shiny, check_last_pokemon, catch_with_safari_strategy,
)
from script_utils.navigation import in_wild, restart, navigate_safari_zone

SEED_MS_MIN    = 33000
SEED_MS_STEP   = 32
NORMAL_MS_MIN  = 10000
NORMAL_MS_STEP = 32

SCAN_RADIUS       = [100, 200, 300]
PROGRESS_INTERVAL = 10
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rng_logs")

# ── user config ───────────────────────────────────────────────────────────────
GAME_VERSION     = "fr_nx"
METHOD           = "Static"   # "Static" | "Wild"
CATEGORY         = "Fossil"   # Static: Gift/Fossil/Stationary/Legend/Event/Game Corner
                              # Wild:   Grass/Surfing/OldRod/GoodRod/SuperRod
LOCATION         = "Fossil"   # Wild: actual location string; Static: same as CATEGORY
POKEMON_SPECIES  = "Omanyte"
# ─────────────────────────────────────────────────────────────────────────────

GIFT_CATEGORIES = {"Gift", "Fossil", "Game Corner"}
BATTLE_CATEGORIES = {"Grass", "Surfing", "OldRod", "GoodRod", "SuperRod", "Stationary", "Legend", "Event"}


SCAN_GAME_SETTINGS = GameSettings.from_string("Mono | Help | Seed Button: A | Extra Button: None")

class ScanConfig:
    def __init__(self, seed_ms, normal_ms):
        self.game_version    = GAME_VERSION
        self.pokemon_species = POKEMON_SPECIES
        self.rng_category    = CATEGORY
        self.rng_location    = LOCATION
        self.rng_method      = "Static 1" if METHOD == "Static" else "Wild 1"
        self.game_settings   = SCAN_GAME_SETTINGS
        self.schedule        = RNGSchedule(
            seed_ms=seed_ms,
            advances_ms_tv=0,
            advances_ms_normal=normal_ms,
        )


def progress_key() -> str:
    return re.sub(r"[^\w]", "_", f"{GAME_VERSION}_{METHOD}_{CATEGORY}_{POKEMON_SPECIES}").lower()


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


def scan_hit(ctx: ScriptContext, cfg: ScanConfig) -> None:
    hit_init_seed(ctx, cfg)
    start = time.time()
    end   = start + cfg.schedule.advances_ms_normal / 1000.0

    if LOCATION.startswith("Safari Zone"):
        zone     = LOCATION.split()[-1].lower()
        category = "Rod" if CATEGORY.endswith("Rod") else CATEGORY
        navigate_safari_zone(ctx, f"{zone}_{category}")

    if CATEGORY in ["Grass", "Surfing"]:
        hit_sweet_scent(ctx, cfg, end)
    elif CATEGORY in ["OldRod", "GoodRod", "SuperRod"]:
        hit_rod(ctx, cfg, end)
    elif CATEGORY == "Game Corner":
        from script_utils.hit import hit_game_corner
        hit_game_corner(ctx, cfg, end)
    elif CATEGORY in ["Gift", "Stationary", "Legend", "Fossil", "Event"]:
        hit_A(ctx, cfg, end)
    else:
        raise NotImplementedError(CATEGORY)


def check_result(ctx: ScriptContext, cfg: ScanConfig) -> bool:
    if LOCATION.startswith("Safari Zone"):
        is_shiny, pokemon_en = check_shiny(ctx, cfg)
        if not is_shiny:
            return False
        ctx.log("shiny in Safari!")
        ctx.press("CAPTURE", 3000)
        ctx.screen_record_start()
        caught = catch_with_safari_strategy(ctx, pokemon_en)
        ctx.screen_record_save()
        if caught:
            ctx.log("捕获成功!")
            return True
        else:
            ctx.log("捕获失败...")
            return False

    if CATEGORY in ["Grass", "Surfing", "SuperRod", "GoodRod", "OldRod", "Stationary", "Legend", "Event"]:
        is_shiny, _ = check_shiny(ctx, cfg)
        return is_shiny

    if CATEGORY in ["Gift", "Fossil", "Game Corner"]:
        check_last_pokemon(ctx)
        return bool(ctx.search_label("FRLG闪光", 80))

    raise NotImplementedError(CATEGORY)


def launch(
    method: str = METHOD,
    category: str = CATEGORY,
    location: str = LOCATION,
    pokemon_species: str = POKEMON_SPECIES,
    game_version: str = GAME_VERSION,
) -> None:
    global METHOD, CATEGORY, LOCATION, POKEMON_SPECIES, GAME_VERSION
    METHOD, CATEGORY, LOCATION, POKEMON_SPECIES, GAME_VERSION = (
        method, category, location, pokemon_species, game_version,
    )

    skip_iters = load_progress()
    if skip_iters:
        print(f"[scan] resuming from skip_iters={skip_iters} (loaded from progress log)")

    def main(ctx: ScriptContext) -> None:
        attempt     = 0
        prev_radius = 0
        total_done  = 0
        for radius in SCAN_RADIUS:
            ctx.log(f"=== scan radius {radius} ===")
            first = (prev_radius == 0 and radius == SCAN_RADIUS[0])
            for si, ni, seed_ms, normal_ms in iter_grid(radius, prev_radius, skip_iters if first else 0):
                if not ctx.is_running():
                    return
                attempt    += 1
                total_done += 1
                cfg = ScanConfig(seed_ms, normal_ms)
                ctx.log(f"#{attempt} seed={seed_ms}ms normal={normal_ms}ms (s{si} n{ni})")

                scan_hit(ctx, cfg)

                if check_result(ctx, cfg):
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
    launch()


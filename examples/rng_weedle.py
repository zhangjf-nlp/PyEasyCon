# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rng.config import GameSettings, RNGConfig, RNGSlot
from examples.rng import launch


cfg = RNGConfig(
    game_version="fr_nx",
    trainer_id=58888,
    secret_id=12232,
    game_settings = GameSettings.from_string(
        "Mono | Help | Seed Button: Start | Extra Button: None"
    ),
    pokemon_species="Weedle",
    rng_category="Grass",
    rng_location="Viridian Forest",
    rng_method="All Wild Methods",
    target=RNGSlot(0x4B95, 0, 1127999),
    seed_bias=-3592,
    advances_bias=-10311,
    normal_ms_min=10000,
    precicase_combos=128,
)

if __name__ == "__main__":
    launch(cfg)
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
        "Mono | Help | Seed Button: A | Extra Button: None"
    ),
    pokemon_species="Snorlax",
    rng_category="Stationary",
    rng_location="Static 1",
    rng_method="Static 1",
    target=RNGSlot(0xA2C5, 0, 263855),
    seed_bias=-3418,
    advances_bias=-10857,
    normal_ms_min=12000,
    max_fast_attempts=0,
)

if __name__ == "__main__":
    launch(cfg)
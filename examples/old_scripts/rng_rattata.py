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
    pokemon_species="Rattata",
    rng_category="Grass",
    rng_location="Route 22",
    rng_method="All Wild Methods",
    target=RNGSlot(0x44B6, 0, 394530),
    seed_bias=-4207,
    advances_bias=-10019,
    normal_ms_min=10000,
)

if __name__ == "__main__":
    launch(cfg)
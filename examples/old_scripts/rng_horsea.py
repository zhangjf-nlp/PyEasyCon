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
    pokemon_species="Horsea",
    rng_category="SuperRod",
    rng_location="Route 24",
    rng_method="All Wild Methods",
    target=RNGSlot(0xA66D, 0, 481832),
    seed_bias=-4266,
    advances_bias=-10768,
    normal_ms_min=18000,
)

if __name__ == "__main__":
    launch(cfg)
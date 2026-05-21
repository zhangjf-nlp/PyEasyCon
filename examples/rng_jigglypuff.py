# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rng.config import GameSettings, RNGConfig, TimingConfig
from examples.rng import launch


cfg = RNGConfig(
    game_version="fr_nx",
    trainer_id=58888,
    secret_id=12232,
    game_settings = GameSettings.from_string(
        "Mono | Help | Seed Button: A | Extra Button: None"
    ),
    pokemon_species="Jigglypuff",
    rng_category="Grass",
    rng_location="Route 3",
    rng_method="All Wild Methods",
    seed_hex="4F70",
    advances=1709801,
    seed_bias=-3942,
    advances_bias=-9553,
    timing=TimingConfig(operation_seconds=10.0),
)

if __name__ == "__main__":
    launch(cfg)
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
    pokemon_species="Gyarados",
    rng_category="SuperRod",
    rng_location="Route 22",
    rng_method="All Wild Methods",
    seed_hex="0D75",
    advances=324980,
    seed_bias=-4266,
    advances_bias=-10768,
    timing=TimingConfig(operation_seconds=12.5),
)

if __name__ == "__main__":
    launch(cfg)
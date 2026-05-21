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
        "Mono | Help | Seed Button: Start | Extra Button: None"
    ),
    pokemon_species="Pikachu",
    rng_category="Grass",
    rng_location="Viridian Forest",
    rng_method="All Wild Methods",
    seed_hex="B235",
    advances=153142,
    seed_bias=-5047,
    advances_bias=-10143,
    timing=TimingConfig(operation_seconds=10.0),
)

if __name__ == "__main__":
    launch(cfg)
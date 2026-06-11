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
    pokemon_species="Dratini",
    rng_category="Game Corner",
    rng_location="Game Corner",
    rng_method="Static 1",
    target=RNGSlot(0xECA1, 0, 183988),
    seed_bias=-4891,
    advances_bias=-11118,
    normal_ms_min=12000,
)

if __name__ == "__main__":
    launch(cfg)
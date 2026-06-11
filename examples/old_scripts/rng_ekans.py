# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rng.config import GameSettings, RNGConfig, RNGSlot, SessionState
from examples.rng import launch


cfg = RNGConfig(
    game_version="fr_nx",
    trainer_id=58888,
    secret_id=12232,
    game_settings = GameSettings.from_string(
        "Mono | Help | Seed Button: A | Extra Button: None"
    ),
    pokemon_species="Ekans",
    rng_category="Grass",
    rng_location="Route 4",
    rng_method="All Wild Methods",
    target=RNGSlot(0xFFAD, 0, 148943),
    seed_bias=-4006,
    advances_bias=-10640,
    normal_ms_min=10000,
)
state = SessionState()

if __name__ == "__main__":
    launch(cfg, state)
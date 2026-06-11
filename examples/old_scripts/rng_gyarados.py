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
        #"Mono | Help | Seed Button: Start | Extra Button: None"
        "Mono | Help | Seed Button: A | Extra Button: None"
    ),
    pokemon_species="Gyarados",
    rng_category="SuperRod",
    rng_location="Route 21",
    rng_method="All Wild Methods",
    #target=RNGSlot(0x8389, 0, 124641),
    target=RNGSlot(0x69CA, 0, 776559),
    seed_bias=-3898,
    advances_bias=-12500,
    normal_ms_min=20000,
)

if __name__ == "__main__":
    launch(cfg)
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rng.config import GameSettings, RNGConfig, TimingConfig, SessionState
from examples.rng import launch


cfg = RNGConfig(
    game_version="fr_nx",
    trainer_id=58888,
    secret_id=12232,
    game_settings = GameSettings.from_string(
        "Mono | Help | Seed Button: Start | Extra Button: None"
    ),
    pokemon_species="Geodude",
    rng_category="Grass",
    rng_location="Mt Moon 1F",
    rng_method="All Wild Methods",
    seed_hex="4B95",
    advances=1128037,
    seed_bias=-3464,
    advances_bias=-11906,
    timing=TimingConfig(operation_seconds=10.0),
)
state = SessionState()

if __name__ == "__main__":
    launch(cfg, state)
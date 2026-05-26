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
        "Mono | Help | Seed Button: Start | Extra Button: None"
    ),
    pokemon_species="Nidoran♂",
    rng_category="Grass",
    rng_location="Route 3",
    rng_method="All Wild Methods",
    target=RNGSlot(0x5F16, 0, 51292),
    seed_bias=-4550,
    advances_bias=-9410,
    normal_ms_min=10000,
)
state = SessionState(
    fast_attempts=0, # 快速尝试次数，期间不进行IV计算和反查校准
)

if __name__ == "__main__":
    launch(cfg, state)
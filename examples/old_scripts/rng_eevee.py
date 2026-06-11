# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rng.config import GameSettings, RNGConfig, RNGSlot, SessionState
from examples.rng import launch


cfg = RNGConfig(
    game_version="fr_nx",
    trainer_id=39349,
    secret_id=19772,
    game_settings = GameSettings.from_string(
        "Mono | Help | Seed Button: Start | Extra Button: None"
    ),
    pokemon_species="Eevee",
    rng_category="Gift",
    rng_location="Gift",
    rng_method="Static 1",
    target=RNGSlot(0x4C88, 0, 371024),
    seed_bias=-4790,
    advances_bias=-11249,
    normal_ms_min=10000,
)
state = SessionState()

if __name__ == "__main__":
    launch(cfg, state)
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from .tenlines_utils import GameSettings, get_seed_time

SEED_PERIOD = 16
ADV_PERIOD = 314


class RNGDisplacement:
    __slots__ = ("ds", "dt", "dn")

    def __init__(self, ds: int, dt: int, dn: int) -> None:
        self.ds = ds
        self.dt = dt
        self.dn = dn

    @property
    def l1(self) -> int:
        return abs(self.ds) + abs(self.dt) + abs(self.dn)

    @property
    def l2(self) -> float:
        return math.sqrt(self.ds ** 2 + self.dt ** 2 + self.dn ** 2)

    def to_array(self) -> np.ndarray:
        return np.array([self.ds, self.dt, self.dn], dtype=float)

    def __repr__(self) -> str:
        return f"RNGDisplacement(ds={self.ds:+d}, dt={self.dt:+d}, dn={self.dn:+d})"


class RNGSlot:
    __slots__ = ("seed_hex", "seed_time", "advances")

    def __init__(self, seed_hex: int, seed_time: int, advances: int) -> None:
        self.seed_hex = seed_hex
        self.seed_time = seed_time
        self.advances = advances

    def __sub__(self, other: "RNGSlot") -> RNGDisplacement:
        delta_s = round((self.seed_time - other.seed_time) / SEED_PERIOD)
        delta_t = round((self.advances - other.advances) / ADV_PERIOD)
        delta_n = self.advances - delta_t * ADV_PERIOD - other.advances
        return RNGDisplacement(delta_s, delta_t, delta_n)

    def __repr__(self) -> str:
        return f"RNGSlot(0x{self.seed_hex:04X}, {self.seed_time}ms, {self.advances})"


@dataclass
class RNGSchedule:
    seed_ms: int
    advances_ms_tv: int
    advances_ms_normal: int
    fps_tv: int = 18840
    fps_normal: int = 120
    normal_ms_min: int = 10000

    def apply_calibration(self, disp: RNGDisplacement) -> None:
        self.seed_ms -= disp.ds * 16
        self.advances_ms_tv -= disp.dt * 16
        self.advances_ms_normal -= disp.dn * 16 / 2

        while self.advances_ms_normal < self.normal_ms_min:
            self.advances_ms_tv -= 16
            self.advances_ms_normal += 16 * (self.fps_tv // self.fps_normal)


@dataclass
class RNGConfig:
    trainer_id: int = 58888
    secret_id: int = 12232
    pokemon_species: str = "Gyarados"
    rng_category: str = "SuperRod"
    rng_location: str = "Route 22"
    rng_method: str = "All Wild Methods"
    game_version: str = "fr_nx"
    game_settings: GameSettings = field(default_factory=lambda: GameSettings.from_string(
        "Mono | Help | Seed Button: A | Extra Button: None"
    ))

    target: RNGSlot = field(default_factory=lambda: RNGSlot(0x0D75, 0, 324980))

    seed_bias: int = -4266
    advances_bias: int = -10768

    fps_seed: int = 1005
    fps_normal: int = 120
    fps_tv: int = 18840
    normal_ms_min: int = 10000

    precicase_combos: int = 64
    coldstart_credits: int = 3
    calibration_credits: int = 10
    max_candies: int = 10
    max_fast_attempts: int = 30

    schedule: RNGSchedule = field(init=False)

    def __post_init__(self) -> None:
        if self.target.seed_time == 0:
            self.target.seed_time = get_seed_time(
                f"{self.target.seed_hex:04X}", self.game_version, self.game_settings
            )

        seed_time_unbiased = self.target.seed_time - self.seed_bias
        seed_ms = int(seed_time_unbiased / self.fps_seed * 1000)

        advances_unbiased = self.target.advances - self.advances_bias
        if self.target.advances < 10000:
            tv_ms = 0
            normal_ms = int(advances_unbiased / self.fps_normal * 1000)
        else:
            advances_operation = self.normal_ms_min * self.fps_normal // 1000
            tv_advances = advances_unbiased - advances_operation
            raw_tv_ms = tv_advances * 1000 // self.fps_tv
            tv_ms = (raw_tv_ms // 16) * 16
            tv_adv_consumed = tv_ms / 1000 * self.fps_tv
            normal_ms = int(
                (tv_advances - tv_adv_consumed) / self.fps_normal * 1000
            )
            while normal_ms < self.normal_ms_min and tv_ms >= 16:
                tv_ms -= 16
                tv_adv_consumed = tv_ms / 1000 * self.fps_tv
                normal_ms = int(
                    (tv_advances - tv_adv_consumed) / self.fps_normal * 1000
                )

        self.schedule = RNGSchedule(
            seed_ms=seed_ms,
            advances_ms_tv=tv_ms,
            advances_ms_normal=normal_ms,
            fps_tv=self.fps_tv,
            fps_normal=self.fps_normal,
            normal_ms_min=self.normal_ms_min,
        )


@dataclass
class SessionState:
    log_dir: Optional[str] = None
    fast_attempts: int = 0
    attempt_index: int = 0
    coldstart_done: bool = False
    attempts_ocr_data: Dict[int, list] = field(default_factory=dict)
    attempts: Dict[int, Any] = field(default_factory=dict)

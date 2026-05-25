from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .tenlines_utils import GameSettings, get_seed_time


@dataclass
class TimingConfig:
    fps_seed: int = 1005
    fps_normal: int = 120
    fps_tv: int = 18840
    operation_seconds: float = 15.0


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

    seed_hex: str = "0D75"
    advances: int = 324980

    seed_bias: int = -4266
    advances_bias: int = -10768

    timing: TimingConfig = field(default_factory=TimingConfig)

    precicase_combos: int = 64
    coldstart_credits: int = 3
    calibration_credits: int = 10
    max_candies: int = 10
    max_fast_attempts: int = 10

    seed_time: int = field(init=False)
    seed_time_unbiased: int = field(init=False)
    seed_ms: int = field(init=False)
    advances_unbiased: int = field(init=False)
    advances_ms_tv: int = field(init=False)
    advances_ms_normal: int = field(init=False)

    def __post_init__(self) -> None:
        self.seed_time = get_seed_time(self.seed_hex, self.game_version, self.game_settings)
        self._recalc()

    def _recalc(self) -> None:
        t = self.timing
        self.seed_time_unbiased = self.seed_time - self.seed_bias
        self.seed_ms = int(self.seed_time_unbiased / t.fps_seed * 1000)
        self.advances_unbiased = self.advances - self.advances_bias
        if self.advances < 10000:
            self.advances_ms_tv = 0
            self.advances_ms_normal = int(self.advances_unbiased / t.fps_normal * 1000)
        else:
            advances_operation = int(t.operation_seconds * t.fps_normal)
            min_normal_ms = int(t.operation_seconds * 1000)
            tv_advances = self.advances_unbiased - advances_operation
            raw_tv_ms = tv_advances * 1000 // t.fps_tv
            self.advances_ms_tv = (raw_tv_ms // 16) * 16
            tv_adv_consumed = self.advances_ms_tv / 1000 * t.fps_tv
            self.advances_ms_normal = int(
                (tv_advances - tv_adv_consumed) / t.fps_normal * 1000
            )
            while self.advances_ms_normal < min_normal_ms and self.advances_ms_tv >= 16:
                self.advances_ms_tv -= 16
                tv_adv_consumed = self.advances_ms_tv / 1000 * t.fps_tv
                self.advances_ms_normal = int(
                    (tv_advances - tv_adv_consumed) / t.fps_normal * 1000
                )

    def apply_calibration(self, seed_delta: int, adv_delta: int) -> None:
        self.seed_bias += seed_delta
        self.advances_bias += adv_delta
        self._recalc()


@dataclass
class SessionState:
    log_dir: Optional[str] = None
    fast_attempts: int = 0
    attempt_index: int = 0
    coldstart_done: bool = False
    attempts_ocr_data: Dict[int, list] = field(default_factory=dict)
    attempts: Dict[int, Any] = field(default_factory=dict)

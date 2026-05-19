from dataclasses import dataclass, field
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
    finetune_per_precicase: int = 3
    max_candies: int = 10

    seed: int = field(init=False)
    seed_unbiased: int = field(init=False)
    seed_ms: int = field(init=False)
    advances_unbiased: int = field(init=False)
    advances_ms_tv: int = field(init=False)
    advances_ms_normal: int = field(init=False)

    def __post_init__(self):
        self.seed = get_seed_time(self.seed_hex, self.game_version, self.game_settings)
        self._recalc()

    def _recalc(self):
        t = self.timing
        self.seed_unbiased = self.seed - self.seed_bias
        self.seed_ms = int(self.seed_unbiased / t.fps_seed * 1000)
        self.advances_unbiased = self.advances - self.advances_bias
        advances_operation = int(t.operation_seconds * t.fps_normal)
        self.advances_ms_tv = (self.advances_unbiased - advances_operation) * 40 // t.fps_tv * 25
        self.advances_ms_normal = int(
            (self.advances_unbiased - self.advances_ms_tv / 1000 * t.fps_tv)
            / t.fps_normal * 1000
        )

    def apply_calibration(self, seed_delta: int, adv_delta: int):
        self.seed_bias += seed_delta

        t = self.timing
        min_normal_ms = int(t.operation_seconds * 1000)
        max_normal_ms = int(t.operation_seconds * 1000 * 1.5)

        new_advances_bias = self.advances_bias + adv_delta
        new_advances_unbiased = self.advances - new_advances_bias

        tv_adv = self.advances_ms_tv / 1000 * t.fps_tv
        normal_remain = new_advances_unbiased - tv_adv
        normal_try = round(normal_remain / t.fps_normal * 1000)

        if min_normal_ms <= normal_try <= max_normal_ms:
            self.advances_bias = new_advances_bias
            self.advances_ms_normal = normal_try
            self.seed_unbiased = self.seed - self.seed_bias
            self.seed_ms = int(self.seed_unbiased / t.fps_seed * 1000)
            self.advances_unbiased = new_advances_unbiased
        else:
            self.advances_bias = new_advances_bias
            self._recalc()


@dataclass
class SessionState:
    log_dir: str = None
    valid_calibration_attempts: int = 0
    calibration_start_count: int = None
    attempts_ocr_data: dict = field(default_factory=dict)

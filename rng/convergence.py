"""
Convergence detection for RNG calibration.

Convergence is declared when the median matches the target and all individual
observations fall on their respective quantization grid around the target.
"""

import numpy as np
from typing import List, Tuple


def check_convergence(
    seed_observations: List[int],
    adv_observations: List[int],
    target_seed: int,
    target_adv: int,
    min_observations: int = 10,
) -> Tuple[bool, bool, int, int]:
    seed_median: int = int(np.median(seed_observations))
    adv_median: int = int(round(np.median(adv_observations)))

    seed_allowed_diffs = {16 * i + j for i in range(-1, 2) for j in range(-1, 1)}
    seed_converged: bool = (
        len(seed_observations) >= min_observations
        and target_seed == seed_median
        and all(o - target_seed in seed_allowed_diffs for o in seed_observations)
    )

    adv_allowed_diffs = {314 * i + j for i in range(-1, 2) for j in range(-4, 5)}
    adv_converged: bool = (
        len(adv_observations) >= min_observations
        and abs(target_adv - adv_median) <= 1
        and all(o - target_adv in adv_allowed_diffs for o in adv_observations)
    )

    return seed_converged, adv_converged, seed_median, adv_median

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from rng.tenlines_utils import (
    calibration as _api,
    iv_calculator,
    GameSettings, IVsObservation, NATURES,
    get_species_id, get_personal,
)
from rng.config import RNGConfig, SessionState

WIDE_SEED_BIAS = 5000
WIDE_ADV_BIAS = 50000

SEED_PERIOD = 16
ADV_PERIOD = 314

_NATURES_LOWER = {n.lower(): n for n in NATURES}


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


def _slot_dist_key(a: RNGSlot, b: RNGSlot) -> Tuple[int, float]:
    d = a - b
    return (d.l1, d.l2)


def _make_slots(results: List) -> List[RNGSlot]:
    return [RNGSlot(int(r.seed, 16), r.seed_time, r.advances) for r in results]


def _obs_to_iv_range(
    obs_list: List[IVsObservation],
    base_stats: Tuple[int, int, int, int, int, int],
) -> Optional[Tuple[List[int], List[int]]]:
    r = iv_calculator(obs_list, base_stats)
    lo = r.ivs_lower_bound
    hi = r.ivs_upper_bound
    lo_list = [lo.hp, lo.attack, lo.defense, lo.sp_attack, lo.sp_defense, lo.speed]
    hi_list = [hi.hp, hi.attack, hi.defense, hi.sp_attack, hi.sp_defense, hi.speed]
    if any(lo_list[i] > hi_list[i] for i in range(6)):
        return None
    return lo_list, hi_list


def n_combos(lo: List[int], hi: List[int]) -> int:
    result = 1
    for i in range(6):
        result *= (hi[i] - lo[i] + 1)
    return result


def _parse_attempt(
    entries: List[dict],
) -> Tuple[List[IVsObservation], str, Optional[str], Optional[str], Optional[int], Optional[str]]:
    obs_list: List[IVsObservation] = []
    nature = "Any"
    gender = None
    ability = None
    caught_level = None
    pokemon = None
    for e in entries:
        if pokemon is None and e.get("pokemon"):
            pokemon = e["pokemon"]
        ocr = e.get("ocr_result", {})
        st = ocr.get("screen", "")
        if st == "CAUGHT_INFO":
            n = (ocr.get("nature") or "").strip()
            if n:
                nature = _NATURES_LOWER.get(n.lower(), n)
            g = (ocr.get("gender") or "").strip().lower()
            if g in ("male", "m"):
                gender = "M"
            elif g in ("female", "f"):
                gender = "F"
            lv = ocr.get("level")
            if lv is not None:
                caught_level = lv
        elif st in ("CAUGHT_IV", "ELEVATED"):
            if st == "CAUGHT_IV":
                ability = (ocr.get("ability") or "").strip().title()
            obs_list.append(IVsObservation(
                nature=nature, level=ocr["level"],
                hp=ocr["hp"], attack=ocr["attack"], defense=ocr["defense"],
                sp_attack=ocr["sp_atk"], sp_defense=ocr["sp_def"], speed=ocr["speed"],
            ))
    return obs_list, nature, gender, ability, caught_level, pokemon


def _search(
    obs_list: List[IVsObservation],
    nature: str,
    gender: Optional[str],
    ability: Optional[str],
    caught_level: Optional[int],
    pokemon: str,
    seed_hex: str,
    advances: int,
    trainer_id: int,
    secret_id: int,
    game_settings: GameSettings,
    seed_bias: int,
    adv_bias: int,
    game: str = "fr_nx",
    method: str = "All Wild Methods",
    location: str = "Route 19",
    category: str = "Surfing",
) -> List:
    return _api(
        game=game, console="NX", tid=trainer_id, sid=secret_id,
        method=method, seed=seed_hex, advances=advances,
        settings=game_settings,
        seed_bias=seed_bias, advances_bias=adv_bias,
        nature=nature, gender=gender, ability=ability,
        location=location, category=category,
        ivs_observations=obs_list, pokemon=pokemon, level=caught_level,
    )


class RNGAttempt:
    def __init__(self, attempt_id: int, entries: List[dict], target: RNGSlot, cfg: RNGConfig) -> None:
        self.id = attempt_id
        self.entries = entries
        self.target = target
        self.cfg = cfg

        self.obs_list, self.nature, self.gender, self.ability, self.caught_level, self.pokemon = \
            _parse_attempt(self.entries)
        if not self.obs_list or self.pokemon is None:
            return
        base_stats = get_personal(get_species_id(self.pokemon))["stats"]
        if _obs_to_iv_range(self.obs_list, base_stats) is None:
            return

        results = _search(
            self.obs_list, self.nature, self.gender, self.ability,
            self.caught_level, self.pokemon,
            self.cfg.seed_hex, self.cfg.advances,
            self.cfg.trainer_id, self.cfg.secret_id, self.cfg.game_settings,
            WIDE_SEED_BIAS, WIDE_ADV_BIAS,
            self.cfg.game_version, self.cfg.rng_method,
            self.cfg.rng_location, self.cfg.rng_category,
        )
        self.slots = _make_slots(results)

        if len(self.slots) == 0:
            print(f"[classify] #{self.id} -> empty")
        elif self.is_precise:
            print(f"[classify] #{self.id} -> precise | unique {self.slots[0] - self.target}")
        else:
            for r in results:
                print(f"[classify] #{self.id} {r}")
            nearest = self.find_nearest(self.target)
            print(f"[classify] #{self.id} -> vague | nearest (1/{len(self.slots)}) {nearest - self.target}")

    @property
    def is_precise(self) -> bool:
        return len(self.slots) == 1

    @property
    def is_valid(self) -> bool:
        return len(self.slots) > 0

    @property
    def credit(self) -> int:
        return 3 if self.is_precise else (1 if self.is_valid else 0)

    def find_nearest(self, slot: RNGSlot) -> RNGSlot:
        return min(self.slots, key=lambda s: _slot_dist_key(s, slot))

    def representative(self) -> Optional[RNGSlot]:
        if not self.slots:
            return None
        return self.find_nearest(self.target)


def calibrate(cfg: RNGConfig, state: SessionState) -> dict:
    attempts = [a for a in state.attempts.values() if a.is_valid]
    if not attempts:
        raise ValueError("无有效观测数据")

    target = RNGSlot(cfg.seed_hex, cfg.seed_time, cfg.advances)

    print(f"[calibrate] {len(attempts)} valid attempts "
          f"({sum(1 for a in attempts if a.is_precise)} precise, "
          f"{sum(1 for a in attempts if not a.is_precise)} vague)")

    reps = [a.representative() for a in attempts]
    seed_to_hex: Dict[int, int] = {}
    for r in reps:
        seed_to_hex[r.seed_time] = r.seed_hex
    seed_times_set = list(seed_to_hex.keys())
    advances_set = list({r.advances for r in reps})

    best_anchor: Optional[RNGSlot] = None
    best_l1: float = float("inf")
    best_l2: float = float("inf")

    for st in seed_times_set:
        hex_val = seed_to_hex[st]
        for a in advances_set:
            candidate = RNGSlot(hex_val, st, a)
            total_l1 = 0.0
            total_l2 = 0.0
            for attempt in attempts:
                nearest = attempt.find_nearest(candidate)
                d = nearest - candidate
                total_l1 += d.l1
                total_l2 += d.l2
            if total_l1 < best_l1 or (total_l1 == best_l1 and total_l2 < best_l2):
                best_l1 = total_l1
                best_l2 = total_l2
                best_anchor = candidate

    anchor = best_anchor
    print(
        f"[calibrate] anchor {repr(anchor)} "
        f"(sum l1={best_l1} l2={best_l2:.2f})"
    )

    observed_slots: List[RNGSlot] = []
    for attempt in attempts:
        nearest = attempt.find_nearest(anchor)
        observed_slots.append(nearest)
        disp = nearest - target
        print(
            f"[calibrate] #{attempt.id}: {nearest} -> {disp}"
        )

    deltas = np.array([(obs - target).to_array() for obs in observed_slots])
    median_deltas = np.median(deltas, axis=0)

    ds = int(round(median_deltas[0]))
    dt = int(round(median_deltas[1]))
    dn = int(round(median_deltas[2]))

    seed_bias_delta = ds * SEED_PERIOD
    adv_bias_delta = dt * ADV_PERIOD + dn

    m0 = np.mean(deltas ** 2, axis=0)
    m_p1 = np.mean((deltas - 1) ** 2, axis=0)
    m_m1 = np.mean((deltas + 1) ** 2, axis=0)
    is_median_zero = np.round(np.median(deltas, axis=0)) == 0
    is_frequent_zero = (deltas == 0).mean(axis=0) * 3 >= 1
    is_mse_lowest = (m0 <= m_p1) & (m0 <= m_m1)
    conv = np.sum([is_median_zero, is_frequent_zero, is_mse_lowest], axis=0) >= 2

    seed_conv = bool(conv[0])
    period_conv = bool(conv[1])
    phase_conv = bool(conv[2])
    adv_conv = period_conv and phase_conv

    print(
        f"[calibrate] median ds={ds} dt={dt} dn={dn} | "
        f"seed_bias_delta={seed_bias_delta:+d}ms adv_bias_delta={adv_bias_delta:+d}"
    )
    print(
        f"[calibrate] conv: seed={seed_conv} period={period_conv} phase={phase_conv}"
    )

    return {
        "seed_bias": seed_bias_delta,
        "adv_bias": adv_bias_delta,
        "seed_converged": seed_conv,
        "advances_converged": adv_conv,
        "anchor": anchor,
        "ds": ds,
        "dt": dt,
        "dn": dn,
    }

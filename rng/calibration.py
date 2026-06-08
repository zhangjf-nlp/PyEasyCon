from typing import Dict, List, Optional, Tuple

import numpy as np

from rng.tenlines_utils import (
    calibration as tenlines_calibration,
    IVsObservation, NATURES, METHOD_NAMES,
)
from rng.config import RNGConfig, SessionState, RNGSlot, SEED_PERIOD, ADV_PERIOD

WIDE_SEED_BIAS = 3000
WIDE_ADV_BIAS = 30000

NATURES_LOWER = {n.lower(): n for n in NATURES}


def make_slots(results: List) -> List[RNGSlot]:
    return [RNGSlot(int(r.seed, 16), r.seed_time, r.advances, METHOD_NAMES.get(r.method, f"Method {r.method}")) for r in results]


def parse_entries(
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
                nature = NATURES_LOWER.get(n.lower(), n)
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


class RNGAttempt:
    def __init__(self, attempt_id: int, entries: List[dict], target: RNGSlot, cfg: RNGConfig) -> None:
        self.id = attempt_id
        self.entries = entries
        self.target = target
        self.cfg = cfg

        self.obs_list, self.nature, self.gender, self.ability, self.caught_level, self.pokemon = \
            parse_entries(self.entries)
        if not self.obs_list or self.pokemon is None:
            return

        results = tenlines_calibration(
            game=self.cfg.game_version,
            console="NX2" if self.cfg.game_version.endswith("nx2") else "NX",
            tid=self.cfg.trainer_id, sid=self.cfg.secret_id,
            method=self.cfg.rng_method,
            seed=f"{self.cfg.target.seed_hex:04X}", advances=self.cfg.target.advances,
            settings=self.cfg.game_settings,
            seed_bias=WIDE_SEED_BIAS, advances_bias=WIDE_ADV_BIAS,
            nature=self.nature, gender=self.gender, ability=self.ability,
            location=self.cfg.rng_location, category=self.cfg.rng_category,
            ivs_observations=self.obs_list, pokemon=self.pokemon, level=self.caught_level,
        )
        self.slots = make_slots(results)

        if len(self.slots) == 0:
            print(f"[classify] #{self.id} -> empty")
        elif self.is_precise:
            print(f"[classify] #{self.id} -> precise ({self.slots[0].method}) | unique {self.slots[0] - self.target}")
        else:
            for r in results:
                print(f"[classify] #{self.id} {r}")
            nearest = self.find_nearest(self.target)
            print(f"[classify] #{self.id} -> vague ({nearest.method}) | nearest (1/{len(self.slots)}) {nearest - self.target}")

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
        return min(self.slots, key=lambda s: s - slot)

    def representative(self) -> Optional[RNGSlot]:
        if not self.slots:
            return None
        return self.find_nearest(self.target)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nature": self.nature,
            "gender": self.gender,
            "ability": self.ability,
            "caught_level": self.caught_level,
            "pokemon": self.pokemon,
            "target": {
                "seed_hex": f"{self.target.seed_hex:04X}",
                "seed_time": self.target.seed_time,
                "advances": self.target.advances,
            },
            "slots": [
                {
                    "seed_hex": f"{s.seed_hex:04X}",
                    "seed_time": s.seed_time,
                    "advances": s.advances,
                    "method": s.method,
                }
                for s in self.slots
            ],
        }


def calibrate(cfg: RNGConfig, state: SessionState) -> dict:
    attempts = [a for a in state.attempts.values() if a.is_valid]
    if not attempts:
        raise ValueError("无有效观测数据")

    target = cfg.target

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
    calibration_lines: List[str] = []
    for attempt in attempts:
        nearest = attempt.find_nearest(anchor)
        observed_slots.append(nearest)
        disp = nearest - target
        line = f"[calibrate] #{attempt.id}: {nearest} ({nearest.method}) -> {disp}"
        print(line)
        calibration_lines.append(line)

    deltas = np.array([(obs - target).to_array() for obs in observed_slots])
    median_deltas = np.median(deltas, axis=0)

    ds = int(median_deltas[0])
    dt = int(median_deltas[1])
    dn = int(median_deltas[2])

    seed_bias_delta = ds * SEED_PERIOD
    adv_bias_delta = dt * ADV_PERIOD + dn

    major_l1 = int((np.abs(deltas).sum(axis=1) <= 3).sum())
    median_l2 = float(ds ** 2 + dt ** 2 + dn ** 2)
    major_l1_converged = major_l1 >= len(attempts) / 2
    median_l2_converged = median_l2 <= 1

    print(
        f"[calibrate] median ds={ds:+d} dt={dt:+d} dn={dn:+d} | "
        f"seed_bias_delta={seed_bias_delta:+d}ms adv_bias_delta={adv_bias_delta:+d}"
    )
    print(
        f"[calibrate] conv: major_l1={major_l1}/{len(attempts)} median_l2={median_l2:.2f} => "
        f"major_l1={major_l1_converged} median_l2={median_l2_converged}"
    )

    return {
        "seed_bias": seed_bias_delta,
        "adv_bias": adv_bias_delta,
        "major_l1_converged": major_l1_converged,
        "median_l2_converged": median_l2_converged,
        "anchor": anchor,
        "ds": ds,
        "dt": dt,
        "dn": dn,
        "calibration_lines": calibration_lines,
    }

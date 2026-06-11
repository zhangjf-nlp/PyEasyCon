from typing import Dict, List, Optional, Tuple

import numpy as np

from rng.tenlines_utils import (
    IVsObservation, NATURES, METHOD_NAMES,
)
from rng.config import RNGConfig, SessionState, RNGSlot, RNGDisplacement, SEED_PERIOD, ADV_PERIOD

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
        is_caught_info = "nature" in ocr and "hp" not in ocr
        is_iv_like = "hp" in ocr and "attack" in ocr and "defense" in ocr
        if is_caught_info:
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
        elif is_iv_like:
            has_ability = "ability" in ocr
            if has_ability:
                ability = (ocr.get("ability") or "").strip().title()
            obs_list.append(IVsObservation(
                nature=nature, level=ocr["level"],
                hp=ocr["hp"], attack=ocr["attack"], defense=ocr["defense"],
                sp_attack=ocr["sp_atk"], sp_defense=ocr["sp_def"], speed=ocr["speed"],
            ))
    return obs_list, nature, gender, ability, caught_level, pokemon


def unique_iv_count(results) -> int:
    seen = set()
    for r in results:
        iv_tuple = (r.ivs.hp, r.ivs.attack, r.ivs.defense, r.ivs.sp_attack, r.ivs.sp_defense, r.ivs.speed)
        seen.add(iv_tuple)
    return len(seen)


class RNGAttempt:
    def __init__(self, attempt_id: int, entries: List[dict], target: RNGSlot, cfg: RNGConfig,
                 candidates=None) -> None:
        self.id = attempt_id
        self.entries = entries
        self.target = target
        self.cfg = cfg
        self.calibration = RNGDisplacement(0, 0, 0)

        self.obs_list, self.nature, self.gender, self.ability, self.caught_level, self.pokemon = \
            parse_entries(self.entries)
        if not self.obs_list or self.pokemon is None or candidates is None:
            self.slots = []
            self.unique_iv_count = 0
        else:
            self.slots = make_slots(candidates)
            self.unique_iv_count = unique_iv_count(candidates) if candidates else 0

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


def calibrate(ctx, cfg: RNGConfig, state: SessionState) -> dict:
    """基于加权正态分布 MLE 的连续校准算法。
    
    每个 attempt 的每个反查结果都对 ds/dt/dn 产生一个正态分布投票，
    方差与 delta 绝对值正相关（ln(|delta|+e)），权重考虑时间衰减和结果数均分。
    取加权概率密度最大的 (ds, dt, dn) 作为本轮修正值。
    """
    attempts: List[RNGAttempt] = sorted(
        [a for a in state.attempts.values() if a.is_valid],
        key=lambda a: a.id,
    )
    if not attempts:
        raise ValueError("无有效观测数据")

    N = len(attempts)
    target = cfg.target

    ctx.log(f"[calibrate] {N} valid attempts "
            f"({sum(1 for a in attempts if a.is_precise)} precise, "
            f"{sum(1 for a in attempts if not a.is_precise)} vague)")

    # ── 1. 展平所有结果，收集权重和delta ──
    weights = []
    deltas = []
    for idx, attempt in enumerate(attempts):
        time_weight = 0.8 ** (N - 1 - idx)
        slot_weight = time_weight / len(attempt.slots)
        weights.extend([slot_weight] * len(attempt.slots))
        for i, slot in enumerate(attempt.slots):
            delta = slot - target - attempt.calibration
            deltas.append(delta.to_array())
            ctx.log(f"# {attempt.id if i==0 else '':<3} - {delta} x {slot_weight:.3f}")

    weights = np.array(weights)                                             # (E,)
    weights = weights / weights.sum()                                       # (E,)
    deltas = np.array(deltas).T                                             # (3, E)

    # ── 2. 一次性广播计算 MLE
    sigma = 2.0
    grid = np.arange(-1000, 1001)                                          # (G,)
    z = (grid[None, :, None] - deltas[:, None, :]) / sigma                 # (3, G, E)
    pdf = np.exp(-0.5 * z * z) / (sigma * np.sqrt(2 * np.pi))              # (3, G, E)
    l = np.einsum('dge,e->dg', pdf, weights)                               # (3, G)
    ml = l.max(axis=1)                                                      # (3,)
    mle = grid[l.argmax(axis=1)]                                            # (3,)
    ds_ml, dt_ml, dn_ml = ml
    ds, dt, dn = mle

    seed_bias_delta = ds * SEED_PERIOD
    adv_bias_delta = dt * ADV_PERIOD + dn

    # 收敛判断：最佳修正值在各维度上都接近 0
    converged = bool(np.all(np.abs(mle) < 2))
    
    ctx.log(
        f"[calibrate] MLE ds={ds:+d} dt={dt:+d} dn={dn:+d} | "
        f"seed_bias_delta={seed_bias_delta:+d}ms adv_bias_delta={adv_bias_delta:+d}"
    )
    ctx.log(
        f"[calibrate] ML ds={ds_ml:.3f} dt={dt_ml:.3f} dn={dn_ml:.3f} | "
        f"{converged=}"
    )

    return {
        "seed_bias": seed_bias_delta,
        "adv_bias": adv_bias_delta,
        "converged": converged,
        "ds": ds,
        "dt": dt,
        "dn": dn,
    }

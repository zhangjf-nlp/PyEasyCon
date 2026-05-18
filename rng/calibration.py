import glob
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

from rng.tenlines_utils import (
    calibration as _calibration_api,
    iv_calculator,
    GameSettings, IVsObservation, NATURES,
    get_species_id, get_personal,
)

MAX_PRECISION_CASES = 5
MAX_PRECISION_COMBOS = 64
ANCHOR_SEED_BIAS = 5000
ANCHOR_ADV_BIAS = 50000
BULK_SEED_BIAS = 100
BULK_ADV_BIAS = 1000

_NATURES_LOWER = {n.lower(): n for n in NATURES}


def _n_combos(lo: List[int], hi: List[int]) -> int:
    c = 1
    for i in range(6):
        c *= (hi[i] - lo[i] + 1)
    return c


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


def _parse_attempt(
    entries: List[dict],
) -> Tuple[List[IVsObservation], str, Optional[str], Optional[str], Optional[int], str]:
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


def _load_attempts(log_dir: str) -> Dict[int, List[dict]]:
    files = sorted(glob.glob(f"{log_dir}/*.json"))
    attempts_data: Dict[int, List[dict]] = {}
    for fn in files:
        with open(fn, "r", encoding="utf-8") as f:
            entry = json.load(f)
        ocr = entry.get("ocr_result", {})
        if ocr.get("screen") not in ("CAUGHT_INFO", "CAUGHT_IV", "ELEVATED"):
            continue
        aid = entry["attempt"]
        attempts_data.setdefault(aid, []).append(entry)
    return attempts_data


def calibrate(
    seed_hex: str,
    seed_time: int,
    advances: int,
    trainer_id: int,
    secret_id: int,
    game_settings: GameSettings,
    game: str = "fr_nx",
    method: str = "All Wild Methods",
    location: str = "Route 19",
    category: str = "Surfing",
    log_dir: Optional[str] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (seed_bias, adv_bias) or (None, None).
    seed_bias: 实际 seed_time 中位数与预期的差值 (ms)
    adv_bias:  实际 advances 中位数与预期的差值 (advances)
    seed_hex:  种子 hex 字符串 (如 "864A")
    seed_time: seed_hex 对应的毫秒时间
    """
    if log_dir is None:
        log_dirs = sorted(glob.glob("rng_logs/20*"))
        if not log_dirs:
            print("[calibration] 未找到 rng_logs 目录")
            return None, None
        log_dir = log_dirs[-1]

    attempts_data = _load_attempts(log_dir)
    all_attempts = []
    for aid in sorted(attempts_data):
        obs_list, nature, gender, ability, caught_level, pokemon = _parse_attempt(attempts_data[aid])
        if not obs_list:
            continue
        if pokemon is None:
            continue
        base_stats = get_personal(get_species_id(pokemon))["stats"]
        iv_range = _obs_to_iv_range(obs_list, base_stats)
        if iv_range is None:
            continue
        lo, hi = iv_range
        all_attempts.append({
            "aid": aid, "obs_list": obs_list, "nature": nature,
            "gender": gender, "ability": ability,
            "lo": lo, "hi": hi, "n_combos": _n_combos(lo, hi),
            "caught_level": caught_level,
            "pokemon": pokemon,
        })

    if not all_attempts:
        print("[calibration] 无有效 attempt")
        return None, None
    
    precision_cases = []
    for attempt in all_attempts:
        if attempt["n_combos"] > MAX_PRECISION_COMBOS:
            continue
        precision_cases.append(attempt)
        if len(precision_cases) >= MAX_PRECISION_CASES:
            break

    print(f"[calibration] {len(all_attempts)} attempts, {len(precision_cases)} precision cases")
    print(f"[calibration] seed_hex={seed_hex} seed_time={seed_time}ms")
    orig_seed_time = seed_time

    # Phase 1: broad search on precision cases
    anchor_candidates: List[Tuple[int, int, int]] = []  # (seed_hex, adv, seed_time)
    for attempt in precision_cases:
        attempt_results = _calibration_api(
            game=game, console="NX", tid=trainer_id, sid=secret_id,
            method=method, seed=seed_hex, advances=advances,
            settings=game_settings,
            seed_bias=ANCHOR_SEED_BIAS, advances_bias=ANCHOR_ADV_BIAS,
            nature=attempt["nature"],
            gender=attempt["gender"], ability=attempt["ability"],
            location=location, category=category,
            ivs_observations=attempt["obs_list"], pokemon=attempt["pokemon"],
            level=attempt["caught_level"],
        )
        if not attempt_results:
            print(f"[calibration] #{attempt['aid']} -> empty results!!!")
            continue
        attempt_seed_times = [r.seed_time for r in attempt_results]
        attempt_advs = [r.advances for r in attempt_results]
        nearest_idx = min(range(len(attempt_results)), key=lambda i: abs(attempt_seed_times[i] - orig_seed_time))
        nearest_seed = int(attempt_results[nearest_idx].seed, 16)
        nearest_seed_time = attempt_seed_times[nearest_idx]
        nearest_advs = min(attempt_advs, key=lambda a: abs(a - advances))
        for result in attempt_results:
            print(f"[calibration] #{attempt['aid']} {result}")
        print(f"[calibration] #{attempt['aid']} 0x{nearest_seed:04X} | {nearest_seed_time}ms {nearest_advs} - nearest")
        anchor_candidates.append((nearest_seed, nearest_advs, nearest_seed_time))

    if not anchor_candidates:
        print("[calibration] Phase 1 无候选")
        return None, None

    if len(anchor_candidates) == 1:
        anchor_seed, anchor_adv, anchor_seed_time = anchor_candidates[0]
    else:
        anchor_seed, anchor_adv, anchor_seed_time = min(
            anchor_candidates,
            key=lambda k: abs(k[2] - orig_seed_time) + abs(k[1] - advances) // 120
        )

    print(f"[calibration] Phase 1 anchor: 0x{anchor_seed:04X} | {anchor_seed_time}ms\t{anchor_adv}")

    # Phase 2: 每个 attempt 计算 seed_time 偏移和 advances 偏移
    all_seed_biases: List[int] = []
    all_adv_biases: List[int] = []
    hits = 0
    for attempt in all_attempts:
        results = _calibration_api(
            game=game, console="NX", tid=trainer_id, sid=secret_id,
            method=method, seed=f"{anchor_seed:04X}", advances=anchor_adv,
            settings=game_settings,
            seed_bias=BULK_SEED_BIAS, advances_bias=BULK_ADV_BIAS,
            nature=attempt["nature"],
            gender=attempt["gender"], ability=attempt["ability"],
            location=location, category=category,
            ivs_observations=attempt["obs_list"], pokemon=attempt["pokemon"],
            level=attempt["caught_level"],
        )
        if not results:
            continue
        result_seed_times = [r.seed_time for r in results]
        result_advs = [r.advances for r in results]
        nearest_idx = min(range(len(results)), key=lambda i: abs(result_seed_times[i] - anchor_seed_time))
        nearest_seed = int(results[nearest_idx].seed, 16)
        nearest_seed_time = result_seed_times[nearest_idx]
        nearest_adv = min(result_advs, key=lambda a: abs(a - anchor_adv))

        all_seed_biases.append(nearest_seed_time - anchor_seed_time)
        all_adv_biases.append(nearest_adv - anchor_adv)
        hits += 1
        print(f"[calibration] #{attempt['aid']}: 0x{nearest_seed:04X} | {nearest_seed_time}ms advances={nearest_adv}")

    if not all_seed_biases:
        print("[calibration] Phase 2 no hit")
        return None, None

    seed_bias = sorted(all_seed_biases)[len(all_seed_biases) // 2] + anchor_seed_time - seed_time
    adv_bias = sorted(all_adv_biases)[len(all_adv_biases) // 2] + anchor_adv - advances
    
    print(f"[calibration] {hits}/{len(all_attempts)} hits  seed_bias={seed_bias:+d}ms  adv_bias={adv_bias:+d}")
    return seed_bias, adv_bias


if __name__ == "__main__":
    seed_bias, adv_bias = calibrate(
        seed_hex="864A",
        seed_time=36919,
        advances=328348,
        trainer_id=58888,
        secret_id=12232,
        game_settings=GameSettings(sound="stereo", button_mode="h", seed_button="a", extra_button="none"),
        game="fr_nx",
        method="All Wild Methods",
        location="Route 19",
        category="Surfing",
        log_dir="rng_logs/20260511_125300",
    )

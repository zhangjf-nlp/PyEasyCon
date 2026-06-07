import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from easycon.config import get
from easycon.context import ScriptContext, sleep
from rng.calibration import calibrate, RNGAttempt
from rng.config import RNGConfig, SessionState, RNGSlot, RNGDisplacement
from rng.tenlines_utils import IVsObservation, get_species_id, get_personal, iv_calculator


def n_combos(lo: List[int], hi: List[int]) -> int:
    result = 1
    for i in range(6):
        result *= (hi[i] - lo[i] + 1)
    return result


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


def init_log_dir(ctx: ScriptContext, state: SessionState, cfg: RNGConfig) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    d = f"rng_logs/{ts}_{cfg.pokemon_species}"
    os.makedirs(d, exist_ok=True)
    os.makedirs(f"{d}/screens", exist_ok=True)
    state.log_dir = d
    ctx.log(f"新建日志目录: {d}")

    cfg_dict = {
        "trainer_id": cfg.trainer_id,
        "secret_id": cfg.secret_id,
        "pokemon_species": cfg.pokemon_species,
        "rng_category": cfg.rng_category,
        "rng_location": cfg.rng_location,
        "rng_method": cfg.rng_method,
        "game_version": cfg.game_version,
        "game_settings": vars(cfg.game_settings) if hasattr(cfg.game_settings, "__dict__") else {},
        "seed_hex": f"{cfg.target.seed_hex:04X}",
        "advances": cfg.target.advances,
        "seed_bias": cfg.seed_bias,
        "advances_bias": cfg.advances_bias,
        "seed_time": cfg.target.seed_time,
        "seed_ms": cfg.schedule.seed_ms,
        "advances_ms_tv": cfg.schedule.advances_ms_tv,
        "advances_ms_normal": cfg.schedule.advances_ms_normal,
        "precicase_combos": cfg.precicase_combos,
        "max_candies": cfg.max_candies,
    }
    with open(f"{d}/settings.json", "w", encoding="utf-8") as f:
        json.dump(cfg_dict, f, ensure_ascii=False, indent=2)
    return d


def save_ocr(state: SessionState, ocr_result: Dict[str, Any], attempt: int, pokemon: str, candy_num: Optional[int] = None) -> None:
    if state.log_dir is None:
        return
    entry = {
        "attempt": attempt,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pokemon": pokemon,
        "ocr_result": ocr_result,
    }
    state.attempts_ocr_data.setdefault(attempt, []).append(entry)


def _make_obs(ocr: Dict[str, Any], nature: str) -> IVsObservation:
    return IVsObservation(
        nature=nature,
        level=ocr["level"],
        hp=ocr["hp"],
        attack=ocr["attack"],
        defense=ocr["defense"],
        sp_attack=ocr["sp_atk"],
        sp_defense=ocr["sp_def"],
        speed=ocr["speed"],
    )


def run_calibration(ctx: ScriptContext, state: SessionState, cfg: RNGConfig) -> None:
    if state.log_dir is None or not state.attempts:
        return

    threshold = cfg.coldstart_credits if not state.coldstart_done else cfg.calibration_credits
    credits = sum(a.credit for a in state.attempts.values())
    if credits < threshold:
        ctx.log(f"[skip] credits={credits}/{threshold} 不足，跳过校准")
        return

    result = calibrate(cfg, state)

    ds = result["ds"]
    dt = result["dt"]
    dn = result["dn"]

    predicted_seed_ms = cfg.schedule.seed_ms - ds * 16
    predicted_tv_ms = cfg.schedule.advances_ms_tv - dt * 16

    seed_ms_min = get("rng.calibration.seed_ms_min", 35000)
    seed_ms_max = get("rng.calibration.seed_ms_max", 60000)
    tv_ms_min = get("rng.calibration.tv_ms_min", 3000)

    if predicted_seed_ms < seed_ms_min:
        ctx.log(f"[reject] Seed takes {predicted_seed_ms}ms < {seed_ms_min}ms")
        return
    if predicted_seed_ms > seed_ms_max:
        ctx.log(f"[reject] Seed takes {predicted_seed_ms}ms > {seed_ms_max}ms")
        return
    if predicted_tv_ms < tv_ms_min and cfg.target.advances >= 10000:
        ctx.log(f"[reject] TV takes {predicted_tv_ms}ms < {tv_ms_min}ms")
        return

    cfg.schedule.apply_calibration(RNGDisplacement(ds=ds, dt=dt, dn=dn))
    cfg.seed_bias += result["seed_bias"]
    cfg.advances_bias += result["adv_bias"]

    ctx.log(f"target: {cfg.target}")
    ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
    ctx.log(
        f"Seed takes {cfg.schedule.seed_ms}ms | TV takes {cfg.schedule.advances_ms_tv}ms "
        f"| Normal takes {cfg.schedule.advances_ms_normal}ms"
    )

    converged = (
        state.coldstart_done
        and result["major_l1_converged"]
        and result["median_l2_converged"]
    )

    if converged:
        state.fast_attempts = cfg.max_fast_attempts
        ctx.log(f"[convergence] fast_attempts={cfg.max_fast_attempts}")
    else:
        state.fast_attempts = 0

    state.coldstart_done = state.coldstart_done or all(abs(result[d]) <= 1 for d in ["ds", "dt", "dn"])
    state.attempts_ocr_data.clear()
    state.attempts.clear()


def observe_pokemon(ctx: ScriptContext, state: SessionState, cfg: RNGConfig, attempt: int, pokemon: str) -> None:
    state.attempt_index = attempt
    if state.log_dir is None:
        init_log_dir(ctx, state, cfg)

    sleep(1.0)
    assert not ctx.search_label('FRLG闪光', 90)
    ocr_caught_info = ctx.ocr_pokemon()
    assert ocr_caught_info.get("screen") == "CAUGHT_INFO"
    nature = ocr_caught_info.get("nature")
    ctx.save_ocr_screenshot(f"{state.log_dir}/screens/{attempt:03d}-CAUGHT_INFO.png", "CAUGHT_INFO")

    gender = (
        "male" if ctx.search_label("FRLG性别符号♂", 90)
        else "female" if ctx.search_label("FRLG性别符号♀", 90)
        else "unknown"
    )
    ocr_caught_info["gender"] = gender
    save_ocr(state, ocr_caught_info, attempt, pokemon)

    sleep(0.5)
    ctx.press("RIGHT")
    sleep(1.0)
    ocr_caught_iv = ctx.ocr_pokemon()
    ocr_caught_iv["gender"] = gender
    assert ocr_caught_iv.get("screen") == "CAUGHT_IV"
    ctx.save_ocr_screenshot(f"{state.log_dir}/screens/{attempt:03d}-CAUGHT_IV.png", "CAUGHT_IV")
    save_ocr(state, ocr_caught_iv, attempt, pokemon)
    sleep(0.5)

    obs_list = [_make_obs(ocr_caught_iv, nature)]

    for i in range(cfg.max_candies):
        if i == 0:
            for _ in range(10):
                ctx.press("B")
                sleep(0.5)
                ctx.press("B")
                sleep(0.5)
                ctx.press("X")
                sleep(1.0)
                if ctx.search_label("FRLG关键词POKeMON", 90):
                    break
            for _ in range(20):
                if ctx.search_label("FRLG关键词BAG选中", 95):
                    break
                ctx.press("DOWN")
                sleep(0.5)
            sleep(1.0)
            ctx.press("A")
            for _ in range(5):
                ctx.press("LEFT")
                sleep(0.5)
                if ctx.search_label("FRLG关键词Items", 90):
                    break
            for _ in range(30):
                if ctx.search_label("FRLG神奇糖果", 90):
                    break
                ctx.press("DOWN")
                sleep(0.5)
            else:
                break

        sleep(1.0)
        ctx.press("A")
        sleep(1.0)
        ctx.press("A")
        sleep(3.0)
        if i == 0:
            ctx.press("UP")
            sleep(1.0)
            ctx.press("UP")
            sleep(1.0)
        ctx.press("A")
        sleep(5.0)
        ctx.press("B")
        sleep(3.0)
        ctx.press("B")
        sleep(1.0)
        ctx.press("B")
        sleep(1.0)
        ocr_elevated = ctx.ocr_pokemon()

        assert ocr_elevated.get("screen") == "ELEVATED"
        ctx.save_ocr_screenshot(f"{state.log_dir}/screens/{attempt:03d}-ELEVATEDx{i+1}.png", "ELEVATED")
        save_ocr(state, ocr_elevated, attempt, pokemon, candy_num=i + 1)

        obs_list.append(_make_obs(ocr_elevated, nature))
        try:
            base_stats = get_personal(get_species_id(pokemon), cfg.game_version)["stats"]
            iv_range = _obs_to_iv_range(obs_list, base_stats)
            if iv_range is not None:
                current_n_combos = n_combos(*iv_range)
                ctx.log(f"{len(obs_list)} IVs observations | {current_n_combos} IVs combos")
                if current_n_combos <= cfg.precicase_combos:
                    break
        except Exception:
            pass

        for _ in range(30):
            ctx.press("B")
            sleep(0.5)
            if ctx.search_label("FRLG神奇糖果", 90):
                break
            if ctx.search_label("FRLG技能替换", 90):
                ctx.press("B")
                sleep(1.0)
                ctx.press("A")
                sleep(0.5)
        else:
            break

    rng_attempt = RNGAttempt(attempt, state.attempts_ocr_data.get(attempt, []), cfg.target, cfg)

    if not rng_attempt.is_valid:
        ctx.log(f"[invalid] #{attempt} -> no result")
        state.attempts_ocr_data.pop(attempt, None)
        return

    state.attempts[attempt] = rng_attempt

    precise_count = sum(1 for a in state.attempts.values() if a.is_precise)
    vague_count = sum(1 for a in state.attempts.values() if not a.is_precise)
    keys = sorted(state.attempts.keys())
    attempt_range = f"#{keys[0]}-{keys[-1]}" if len(keys) > 1 else f"#{keys[0]}"
    total_credits = sum(a.credit for a in state.attempts.values())
    threshold = cfg.coldstart_credits if not state.coldstart_done else cfg.calibration_credits
    ctx.log(f"{attempt_range} {precise_count}p/{vague_count}v => credits={total_credits}/{threshold}")

    if rng_attempt.is_precise:
        ctx.log(f"[precise] #{attempt} -> unique slot")


def ready_for_calibration(state: SessionState, cfg: RNGConfig) -> bool:
    credits = sum(a.credit for a in state.attempts.values())
    threshold = cfg.coldstart_credits if not state.coldstart_done else cfg.calibration_credits
    return credits >= threshold

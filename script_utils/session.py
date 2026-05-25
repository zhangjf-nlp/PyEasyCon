import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from easycon.config import get
from easycon.context import ScriptContext
from rng.calibration import calibrate, n_combos, _obs_to_iv_range, RNGAttempt, RNGSlot
from rng.config import RNGConfig, SessionState
from rng.tenlines_utils import IVsObservation, get_species_id, get_personal
from script_utils.hit import sleep


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
        "seed_hex": cfg.seed_hex,
        "advances": cfg.advances,
        "seed_bias": cfg.seed_bias,
        "advances_bias": cfg.advances_bias,
        "timing": asdict(cfg.timing),
        "precicase_combos": cfg.precicase_combos,
        "max_candies": cfg.max_candies,
        "seed_time": cfg.seed_time,
        "seed_time_unbiased": cfg.seed_time_unbiased,
        "seed_ms": cfg.seed_ms,
        "advances_unbiased": cfg.advances_unbiased,
        "advances_ms_tv": cfg.advances_ms_tv,
        "advances_ms_normal": cfg.advances_ms_normal,
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

    t = cfg.timing
    new_seed_bias = cfg.seed_bias + result["seed_bias"]
    new_seed_time_unbiased = cfg.seed_time - new_seed_bias
    new_seed_ms = int(new_seed_time_unbiased / t.fps_seed * 1000)

    new_adv_unbiased = cfg.advances - (cfg.advances_bias + result["adv_bias"])
    if cfg.advances < 10000:
        new_adv_ms_tv = 0
    else:
        advances_operation = int(t.operation_seconds * t.fps_normal)
        raw_tv_ms = (new_adv_unbiased - advances_operation) * 1000 // t.fps_tv
        new_adv_ms_tv = (raw_tv_ms // 16) * 16

    seed_ms_min = get("rng.calibration.seed_ms_min", 35000)
    seed_ms_max = get("rng.calibration.seed_ms_max", 60000)
    tv_ms_min = get("rng.calibration.tv_ms_min", 3000)

    if new_seed_ms < seed_ms_min:
        ctx.log(f"[reject] Seed takes {new_seed_ms}ms < {seed_ms_min}ms，拒绝校准")
        return
    if new_seed_ms > seed_ms_max:
        ctx.log(f"[reject] Seed takes {new_seed_ms}ms > {seed_ms_max}ms，拒绝校准")
        return
    if new_adv_ms_tv < tv_ms_min:
        ctx.log(f"[reject] TV takes {new_adv_ms_tv}ms < {tv_ms_min}ms，拒绝校准")
        return

    cfg.apply_calibration(result["seed_bias"], result["adv_bias"])
    ctx.log(f"SeedTime={cfg.seed_time}ms Advances={cfg.advances}")
    ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
    ctx.log(
        f"Seed takes {cfg.seed_ms}ms | TV takes {cfg.advances_ms_tv}ms "
        f"| Normal takes {cfg.advances_ms_normal}ms"
    )

    if result["seed_converged"] and result["advances_converged"]:
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
    assert not ctx.search_label('3代闪光', 90)
    ocr_caught_info = ctx.ocr_pokemon()
    assert ocr_caught_info.get("screen") == "CAUGHT_INFO"
    nature = ocr_caught_info.get("nature")
    ctx.save_ocr_screenshot(f"{state.log_dir}/screens/{attempt:03d}-CAUGHT_INFO.png", "CAUGHT_INFO")

    gender = (
        "male" if ctx.search_label("3代性别符号♂", 98)
        else "female" if ctx.search_label("3代性别符号♀", 98)
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
                if ctx.search_label("3代关键词POKeMON", 95):
                    break
            for _ in range(20):
                if ctx.search_label("3代关键词BAG选中", 97):
                    break
                ctx.press("DOWN")
                sleep(0.5)
            sleep(1.0)
            ctx.press("A")
            for _ in range(5):
                ctx.press("LEFT")
                sleep(0.5)
                if ctx.search_label("3代关键词Items", 95):
                    break
            for _ in range(30):
                if ctx.search_label("3代神奇糖果", 95):
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
        sleep(3.0)

        for _ in range(10):
            ctx.press("B")
            sleep(1.0)
            if ctx.search_label("3代升级能力值", 97):
                ctx.press("B")
                sleep(0.5)
                ocr_elevated = ctx.ocr_pokemon()
                break
        else:
            break

        assert ocr_elevated.get("screen") == "ELEVATED"
        ctx.save_ocr_screenshot(f"{state.log_dir}/screens/{attempt:03d}-ELEVATEDx{i+1}.png", "ELEVATED")
        save_ocr(state, ocr_elevated, attempt, pokemon, candy_num=i + 1)

        obs_list.append(_make_obs(ocr_elevated, nature))
        try:
            base_stats = get_personal(get_species_id(pokemon))["stats"]
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
            if ctx.search_label("3代神奇糖果", 95):
                break
            if ctx.search_label("3代技能替换", 95):
                ctx.press("B")
                sleep(1.0)
                ctx.press("A")
                sleep(0.5)
        else:
            break

    target = RNGSlot(0, cfg.seed_time, cfg.advances)
    rng_attempt = RNGAttempt(attempt, state.attempts_ocr_data.get(attempt, []), target, cfg)

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

import json
import os
import time
from dataclasses import asdict

from rng.calibration import calibrate, _obs_to_iv_range, _n_combos
from rng.convergence import check_convergence, T_S, SIGMA_S_DEFAULT, SIGMA_T_DEFAULT, SIGMA_N_DEFAULT
from rng.tenlines_utils import IVsObservation, get_species_id, get_personal
from script_utils.hit import sleep


def init_log_dir(ctx, state, cfg):
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
        "finetune_per_precicase": cfg.finetune_per_precicase,
        "max_candies": cfg.max_candies,
        "seed": cfg.seed,
        "seed_unbiased": cfg.seed_unbiased,
        "seed_ms": cfg.seed_ms,
        "advances_unbiased": cfg.advances_unbiased,
        "advances_ms_tv": cfg.advances_ms_tv,
        "advances_ms_normal": cfg.advances_ms_normal,
    }
    with open(f"{d}/settings.json", "w", encoding="utf-8") as f:
        json.dump(cfg_dict, f, ensure_ascii=False, indent=2)
    return d


def save_ocr(state, ocr_result, attempt, pokemon, candy_num=None):
    if state.log_dir is None:
        return
    entry = {
        "attempt": attempt,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pokemon": pokemon,
        "ocr_result": ocr_result,
    }
    state.attempts_ocr_data.setdefault(attempt, []).append(entry)


def calculate_n_combos(obs_list, pokemon):
    base_stats = get_personal(get_species_id(pokemon))["stats"]
    iv_range = _obs_to_iv_range(obs_list, base_stats)
    if iv_range is None:
        return 0
    lo, hi = iv_range
    return _n_combos(lo, hi)


def run_calibration(ctx, state, cfg):
    if state.log_dir is None:
        return
    if not state.attempts_ocr_data:
        return

    seed_delta, adv_delta, seed_obs, adv_obs = calibrate(
        seed_hex=cfg.seed_hex,
        seed_time=cfg.seed,
        advances=cfg.advances,
        trainer_id=cfg.trainer_id,
        secret_id=cfg.secret_id,
        game_settings=cfg.game_settings,
        game=cfg.game_version,
        method=cfg.rng_method,
        location=cfg.rng_location,
        category=cfg.rng_category,
        log_dir=state.log_dir,
        seed_ms=cfg.seed_ms,
        advances_ms_tv=cfg.advances_ms_tv,
        advances_ms_normal=cfg.advances_ms_normal,
        attempts_data=state.attempts_ocr_data,
    )

    if seed_delta is not None:
        cfg.apply_calibration(seed_delta, adv_delta)
        state.seed_observations.extend(seed_obs)
        state.adv_observations.extend(adv_obs)
        ctx.log(f"校准: seed_delta={seed_delta:+d} adv_delta={adv_delta:+d}")
        ctx.log(f"Seed={cfg.seed}ms Advances={cfg.advances}")
        ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
        ctx.log(
            f"Seed takes {cfg.seed_ms}ms | TV takes {cfg.advances_ms_tv}ms "
            f"| Normal takes {cfg.advances_ms_normal}ms"
        )
        check_calibration_convergence(ctx, state, cfg)
        state.valid_calibration_attempts = 0
        state.calibration_start_count = None
        state.attempts_ocr_data = {}
    else:
        ctx.log("校准失败 (数据不足)")


def check_calibration_convergence(ctx, state, cfg):
    seed_obs = state.seed_observations
    adv_obs = state.adv_observations
    if len(seed_obs) < 10:
        return
    seed_obs = seed_obs[-10:]
    adv_obs = adv_obs[-10:]

    target_seed = float(cfg.seed)
    target_adv = cfg.advances

    both_ok, seed_ok, tv_ok, n_ok, mu_s, mu_t, mu_n = check_convergence(
        seed_observations=seed_obs,
        adv_observations=adv_obs,
        target_seed=target_seed,
        target_adv=target_adv,
    )

    print(
        f"[convergence] Target: Seed={cfg.seed}ms | Advances={cfg.advances}"
    )
    print(
        f"[convergence] Observed Seed: {seed_obs}"
    )
    print(
        f"[convergence] Observed Advances: {adv_obs}"
    )
    print(
        f"[convergence] Estimation: μ_s={mu_s:.1f}ms (σ_s={SIGMA_S_DEFAULT}, T_s={T_S})" if mu_s is not None
        else f"[convergence] Estimation: μ_s=unk (σ_s={SIGMA_S_DEFAULT}, T_s={T_S})"
    )
    print(
        f"[convergence] Estimation: μ_t={mu_t:.2f} (σ_t={SIGMA_T_DEFAULT})  "
        f"μ_n={mu_n:.1f}ms (σ_n={SIGMA_N_DEFAULT})" if mu_t is not None and mu_n is not None
        else f"[convergence] Estimation: μ_t=unk (σ_t={SIGMA_T_DEFAULT})  μ_n=unk (σ_n={SIGMA_N_DEFAULT})"
    )

    if mu_s is not None:
        print(
            f"[Convergence] Maximum Point: Seed={mu_s:.1f}ms | "
            f"z_tv={round(mu_t) if mu_t is not None else '?'} | "
            f"z_n={round(mu_n) if mu_n is not None else '?'}ms | "
            f"Advances={round(mu_t) * 157 + round(mu_n) if mu_t is not None and mu_n is not None else '?'}"
        )
    else:
        print(f"[Convergence] Maximum Point: unk")

    print(
        f"[convergence] Seed: {seed_ok} | Advances: {tv_ok} | Converged: {both_ok}"
    )

    if both_ok:
        state.converged = state.max_fast_tries
        state.seed_observations = seed_obs[-5:] if len(seed_obs) >= 5 else list(seed_obs)
        state.adv_observations = adv_obs[-5:] if len(adv_obs) >= 5 else list(adv_obs)
        print(f"[Convergence] Converged -> Fast Attempts = {state.max_fast_tries}")
    else:
        state.converged = 0


def _make_obs(ocr, nature):
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


def record_for_finetune(ctx, state, cfg, attempt, pokemon):
    if state.log_dir is None:
        init_log_dir(ctx, state, cfg)
        state.calibration_start_count = attempt

    sleep(1.0)
    assert not ctx.search_label('3代闪光', 90)
    ocr_caught_info = ctx.ocr_pokemon()
    assert ocr_caught_info.get("screen") == "CAUGHT_INFO"
    nature = ocr_caught_info.get("nature")
    ctx.save_ocr_screenshot(f"{state.log_dir}/screens/{attempt:03d}-CAUGHT_INFO.png", "CAUGHT_INFO")

    gender = (
        "male"
        if ctx.search_label("3代性别符号♂", 98)
        else "female"
        if ctx.search_label("3代性别符号♀", 98)
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
        current_n_combos = calculate_n_combos(obs_list, pokemon)
        ctx.log(f"{len(obs_list)} IVs observations | {current_n_combos} IVs combos")
        if current_n_combos <= cfg.precicase_combos:
            state.valid_calibration_attempts += 1
            break

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

    ctx.log(f"{attempt} attempts | {state.valid_calibration_attempts} precise observations")
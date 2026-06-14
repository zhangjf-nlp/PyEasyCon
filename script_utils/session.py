import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from easycon.config import get
from easycon.context import ScriptContext
from easycon.controller import sleep
from rng.calibration import calibrate, RNGAttempt, WIDE_SEED_BIAS, WIDE_ADV_BIAS, unique_iv_count
from rng.config import RNGConfig, SessionState, RNGSlot, RNGDisplacement
from rng.tenlines_utils import IVsObservation, get_species_id, get_personal, iv_calculator, calibration as calibration_api, CalibrationResult


def n_combos(lo: List[int], hi: List[int]) -> int:
    result = 1
    for i in range(6):
        result *= (hi[i] - lo[i] + 1)
    return result


def obs_to_ivs_range(
    obs_list: List[IVsObservation],
    base_stats: Tuple[int, int, int, int, int, int],
) -> Optional[Tuple[List[int], List[int]]]:
    if not all(obs.is_valid for obs in obs_list):
        return None
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
    os.makedirs(f"{d}/attempts", exist_ok=True)
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


def save_ocr(state: SessionState, ocr_result: Dict[str, Any], attempt_index: int, pokemon: str, candy_num: Optional[int] = None) -> dict:
    if state.log_dir is None:
        return {}
    entry = {
        "attempt_index": attempt_index,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pokemon": pokemon,
        "ocr_result": ocr_result,
    }
    # 写入 JSONL
    jsonl_path = os.path.join(state.log_dir, "attempts", f"{attempt_index:03d}-ocr.jsonl")
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def make_obs(ocr: Dict[str, Any], nature: str) -> IVsObservation:
    return IVsObservation(
        nature=nature.title(),
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

    current = state.attempts.get(state.attempt_index)
    if current is None or not current.is_valid:
        ctx.log(f"[skip] #{state.attempt_index} 当前轮次无有效观测")
        return

    result = calibrate(ctx, cfg, state)
    calibration = result["displacement"]

    new_seed_ms = cfg.schedule.seed_ms - calibration.ds * 16
    new_tv_ms = cfg.schedule.advances_ms_tv - calibration.dt * 16

    seed_ms_min = get("rng.calibration.seed_ms_min", 35000)
    seed_ms_max = get("rng.calibration.seed_ms_max", 60000)
    tv_ms_min = get("rng.calibration.tv_ms_min", 3000)

    if new_seed_ms < seed_ms_min:
        ctx.log(f"[reject] Seed takes {new_seed_ms}ms < {seed_ms_min}ms")
        state.attempts.pop()
    if new_seed_ms > seed_ms_max:
        ctx.log(f"[reject] Seed takes {new_seed_ms}ms > {seed_ms_max}ms")
        state.attempts.pop()
    if new_tv_ms < tv_ms_min:
        ctx.log(f"[reject] TV takes {new_tv_ms}ms < {tv_ms_min}ms")
        state.attempts.pop()
    else:
        cfg.schedule.apply_calibration(calibration)
        cfg.seed_bias += result["seed_bias"]
        cfg.advances_bias += result["adv_bias"]
        for a in state.attempts.values():
            a.calibration += calibration
        ctx.log(f"target: {cfg.target}")
        ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
        ctx.log(f"Seed takes {cfg.schedule.seed_ms}ms | "
                f"TV takes {cfg.schedule.advances_ms_tv}ms | "
                f"Normal takes {cfg.schedule.advances_ms_normal}ms")
        if result["converged"]:
            state.fast_attempts = cfg.max_fast_attempts
            ctx.log(f"[convergence] fast_attempts={cfg.max_fast_attempts}")


def observe_pokemon(ctx: ScriptContext, state: SessionState, cfg: RNGConfig, attempt_index: int, pokemon: str) -> None:
    state.attempt_index = attempt_index
    if state.log_dir is None:
        init_log_dir(ctx, state, cfg)

    ocr_data: Dict[int, list] = {}

    sleep(1.0)
    if ctx.search_label('FRLG闪光', 90):
        raise ValueError(f"[异常] 队末精灵为异色 -> 停止运行")
    ocr_caught_info = ctx.ocr("CAUGHT_INFO", save_path=f"{state.log_dir}/screens/{attempt_index:03d}-CAUGHT_INFO.png")
    nature = ocr_caught_info.get("nature", "unknown")
    gender = (
        "male" if ctx.search_label("FRLG性别符号♂", 90)
        else "female" if ctx.search_label("FRLG性别符号♀", 90)
        else "unknown"
    )
    ocr_caught_info["gender"] = gender
    ocr_data.setdefault(attempt_index, []).append(
        save_ocr(state, ocr_caught_info, attempt_index, pokemon)
    )

    sleep(0.5)
    ctx.press("RIGHT")
    sleep(2.0)
    ocr_caught_iv = ctx.ocr("CAUGHT_IV", save_path=f"{state.log_dir}/screens/{attempt_index:03d}-CAUGHT_IV.png")
    ocr_caught_iv["gender"] = gender
    ocr_data.setdefault(attempt_index, []).append(
        save_ocr(state, ocr_caught_iv, attempt_index, pokemon)
    )

    obs_list = [make_obs(ocr_caught_iv, nature)]

    # 宝可梦基础种族值（用于 n_combos 判定是否触发搜索）
    pokemon_base_stats = get_personal(get_species_id(pokemon), cfg.game_version)["stats"]

    # 候选结果列表（首次宽搜索后不断用 ivs_range 筛选缩小）
    candidates: Optional[List[CalibrationResult]] = None
    allow_skip = 1  # ELEVATED OCR 偶发错误时允许跳过当次观测的次数

    def find_candidates(olist: list):
        return calibration_api(
            game=cfg.game_version,
            console="NX2" if cfg.game_version.endswith("nx2") else "NX",
            tid=cfg.trainer_id, sid=cfg.secret_id,
            method=cfg.rng_method,
            seed=f"{cfg.target.seed_hex:04X}", advances=cfg.target.advances,
            settings=cfg.game_settings,
            seed_bias=WIDE_SEED_BIAS, advances_bias=WIDE_ADV_BIAS,
            nature=nature, gender=ocr_caught_iv.get("gender", ""),
            ability=ocr_caught_info.get("ability", ""),
            location=cfg.rng_location, category=cfg.rng_category,
            ivs_observations=olist, pokemon=pokemon, level=ocr_caught_info.get("level"),
        )

    sleep(0.5)
    for i in range(cfg.max_candies):
        # ── 导航到糖果并喂糖 ──
        if i == 0:
            for _ in range(10):
                ctx.press("B")
                sleep(0.5)
                ctx.press("B")
                sleep(0.5)
                ctx.press("X")
                sleep(1.0)
                if ctx.search_label("FRLG菜单", 90):
                    break
            for _ in range(20):
                if ctx.search_label("FRLG关键词BAG选中", 95):
                    break
                ctx.press("DOWN")
                sleep(1.0)
            ctx.press("A")
            sleep(1.0)
            for _ in range(5):
                ctx.press("LEFT")
                sleep(0.5)
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
        sleep(1.5)
        ctx.press("B")
        sleep(1.5)
        ocr_elevated = ctx.ocr("ELEVATED", save_path=f"{state.log_dir}/screens/{attempt_index:03d}-ELEVATEDx{i+1}.png")

        ocr_data.setdefault(attempt_index, []).append(
            save_ocr(state, ocr_elevated, attempt_index, pokemon, candy_num=i + 1)
        )

        new_obs = make_obs(ocr_elevated, nature)
        obs_list.append(new_obs)
        n_obs = len(obs_list)

        # ── IV 范围计算 & 候选筛选 ──
        ivs_range = obs_to_ivs_range(obs_list, pokemon_base_stats)
        if ivs_range is None:
            if allow_skip:
                allow_skip = 0
                ctx.log(f"[skip] ELEVATED OCR 无效 (obs#{n_obs})，丢弃本次观测")
                obs_list.pop()
                continue
            else:
                ctx.log(f"{n_obs} IVs observations | IV range invalid -> Check {state.log_dir}")
                return None

        if candidates is None:
            combos = n_combos(*ivs_range)
            ctx.log(f"{n_obs} IVs observations | {combos} IV combos")
            if combos <= cfg.precicase_combos:
                candidates = find_candidates(obs_list)
                uv = unique_iv_count(candidates) if candidates else 0
                ctx.log(f"{n_obs} IVs observations | {uv} IV results")
                candies_no_progress = 0
            else:
                uv = None
        else:
            new_candidates = [r for r in candidates if r.match_ivs_range(ivs_range)]
            new_uv = unique_iv_count(new_candidates) if new_candidates else 0
            ctx.log(f"{n_obs} IVs observations | {new_uv} IV results")
            if new_uv == 0:
                if allow_skip:
                    allow_skip -= 1
                    ctx.log(f"[skip] 丢弃本次观测")
                    obs_list.pop()
                    continue
                else:
                    ctx.log(f"[invalid] 观测异常 -> 样本日志见 {state.log_dir}")
                    return None
            if new_uv > uv:
                raise ValueError(f"{new_uv} > {uv}")
            elif new_uv == uv:
                candies_no_progress += 1
            else:
                uv = new_uv
            candidates = new_candidates
        
        if uv is not None and (uv <= 1 or candies_no_progress >= 3):
            break

        # ── 返回糖果菜单 ──
        for _ in range(30):
            ctx.press("B")
            sleep(3.0)
            if ctx.search_label("FRLG神奇糖果", 90):
                break
            if ctx.search_label("FRLG技能替换", 90):
                ctx.press("B")
                sleep(1.0)
                ctx.press("A")
                sleep(0.5)
        else:
            break

    if candidates is None and len(obs_list) >= 1:
        candidates = find_candidates(obs_list)
        uv = unique_iv_count(candidates) if candidates else 0
        ctx.log(f"{len(obs_list)} IVs observations | {uv} IV results")
    
    dist = lambda r: (RNGSlot(int(r.seed, 16), r.seed_time, r.advances) - cfg.target).l1
    candidates = sorted(candidates, key=dist)[:3]

    rng_attempt = RNGAttempt(attempt_index, ocr_data.get(attempt_index, []), cfg.target, cfg, candidates=candidates)

    if not rng_attempt.is_valid:
        ctx.log(f"[invalid] #{attempt_index} -> no result")
        ocr_data.pop(attempt_index, None)
        return

    state.attempts[attempt_index] = rng_attempt

    if state.log_dir:
        attempt_path = f"{state.log_dir}/attempts/{attempt_index:03d}.json"
        with open(attempt_path, "w", encoding="utf-8") as f:
            json.dump(rng_attempt.to_dict(), f, ensure_ascii=False, indent=2)
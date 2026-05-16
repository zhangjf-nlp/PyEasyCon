# =======================================================================
# EasyCon RNG Hunting — Gen3 乱数狩猎 + OCR 记录 + 自动反查校准
# =======================================================================
# 运行方式: python demo_script.py
# 从 gui 模块导入:
#   is_running()       — while 循环条件
#   press(key, ms=50)  — 点击按键 (A/B/X/Y/L/R/ZL/ZR/UP/DOWN/LEFT/RIGHT/HOME/CAPTURE/PLUS/MINUS)
#   hold(key)          — 按住不释放
#   release(key)       — 释放按键
#   capture()          — NS 截图
#   log(msg)           — 输出日志
#   search_label(name, threshold=80) -> bool (threshold>=0) / int (threshold=-1)
#   ocr_pokemon()      — 自动检测画面并 OCR (ELEVATED/CAUGHT_INFO/CAUGHT_IV)
#   get_frame()        — 获取采集卡当前帧
#   wait(ms)           — 可中断等待
# =======================================================================

import time, json, os, glob, shutil

from gui import press, hold, release, capture, wait, log, search_label, is_running, ocr_pokemon, get_frame
from gui import run_script

from calibration import calibrate, _obs_to_iv_range, _n_combos
from modules.tenlines.tenlines_utils import IVsObservation, GameSettings, get_species_id, get_personal, get_seed_time, get_species_zh_name, get_species_en_name, get_encounter_species_list


def sleep(seconds, end=None):
    start = time.time()
    if end is None:
        mid = start + seconds - 0.1
        end = start + seconds
    else:
        mid = end - 0.1
    while True:
        if time.time() >= mid:
            if time.time() >= end:
                return
            else:
                pass
        else:
            time.sleep(0.05)

# ---------- 脚本设定 ----------
PRECICASE_COMBOS = 64          # 精确个体值组合数上限
FINETUNE_PER_PRECICASE = 3     # 反查校准间隔
MAX_CANDIES = 10               # 神奇糖果次数上限

# 记录符合条件的attempt次数
valid_calibration_attempts = 0
calibration_start_count = None

# ---------- 乱数设定 ----------
TRAINER_ID = 58888
SECRET_ID = 12232
POKEMON_SPECIES = 'Gyarados'
RNG_CATEGORY = 'SuperRod'
RNG_LOCATION = 'Route 22'
RNG_METHOD = 'All Wild Methods'
GAME_VERSION = 'fr_nx'
GAME_SETTINGS = GameSettings.from_string(
    'Mono | Help | Seed Button: A | Extra Button: None'
)

# ---------- 乱数目标 ----------
SEED_HEX = "0D75"                  # 一阶段预期命中Seed
ADVANCES = 324980                  # 二阶段预期消耗帧数

SEED_BIAS = -4266                  # 一阶段系统偏差帧数
FPS_SEED = 1005                    # 一阶段Seed模式帧率
ADVANCES_BIAS = -10768             # 二阶段系统偏差帧数
FPS_NORMAL = 2 * 60                # 二阶段普通模式帧率
FPS_TV = 314 * 60                  # 二阶段TTV模式帧率
ADVANCES_NORMAL = FPS_NORMAL * 15  # 二阶段固定操作帧数

SEED = get_seed_time(SEED_HEX, GAME_VERSION, GAME_SETTINGS)
SEED_UNBIASED = SEED - SEED_BIAS
SEED_MS = int(SEED_UNBIASED / FPS_SEED * 1000)

ADVANCES_UNBIASED = ADVANCES - ADVANCES_BIAS
ADVANCES_MS_TV = (ADVANCES_UNBIASED - ADVANCES_NORMAL) * 8 // FPS_TV * 125
ADVANCES_MS_NORMAL = int((ADVANCES_UNBIASED - ADVANCES_MS_TV / 1000 * FPS_TV) / FPS_NORMAL * 1000)

# ---------- 命中函数 ----------
def hit_init_seed():
    sb, eb = GAME_SETTINGS.seed_button, GAME_SETTINGS.extra_button
    press('A'); sleep(0.1)
    if eb in ['blackout_r', 'blackout_l']:
        log(f'hold {eb[-1].upper()}')
        hold(eb[-1].upper())
    sleep(SEED_MS / 1000.0)
    if eb in ['blackout_r', 'blackout_l']:
        log(f'release {eb[-1].upper()}')
        release(eb[-1].upper())
    if sb == "start":
        hold('PLUS'); sleep(4.0); release('PLUS')
    else:
        assert sb in ['a', 'l'], sb
        hold(sb.upper()); sleep(4.0); release(sb.upper())
    sleep(1.0); press('A'); sleep(1.0); press('B'); sleep(3.0)

def hit_tv_frame():
    press('Y')
    sleep(ADVANCES_MS_TV / 1000.0)
    press('B'); sleep(1.0)

def hit_sweet_scent():
    # 队首精灵释放甜甜香气
    start = time.time()
    end = start + ADVANCES_MS_NORMAL / 1000.0
    press('X'); sleep(1.0); press('DOWN'); sleep(0.5)
    press('A'); sleep(2.0); press('A'); sleep(1.5)
    press('DOWN')
    sleep(0.0, end)
    press('A')

def hit_super_rod():
    # 打开背包使用超级钓竿
    start = time.time()
    end = start + ADVANCES_MS_NORMAL / 1000.0
    press('X'); sleep(1.0); press('DOWN'); sleep(0.5); press('DOWN'); sleep(0.5)
    press('A'); sleep(2.0); press('RIGHT'); sleep(1.0)
    assert search_label('3代关键词KeyItems', 95), search_label('3代关键词KeyItems', -1)
    while not search_label('3代关键词SuperRod选中', 99):
        press('DOWN'); sleep(0.5)
    press('A'); sleep(0.5); press('A')
    sleep(0.0, end)
    press('A')

def hit_gift():
    # 直接领取
    start = time.time()
    end = start + ADVANCES_MS_NORMAL / 1000.0
    sleep(0.0, end)
    press('A'); sleep(3.0); press('B')

# ---------- RNG 流程 ----------
def hit():
    log('--- RNG 流程启动 ---')
    hit_init_seed()
    hit_tv_frame()
    if RNG_CATEGORY in ["Grass", "Surfing"]:
        hit_sweet_scent()
    elif RNG_CATEGORY in ["SuperRod"]:
        hit_super_rod()
    elif RNG_CATEGORY in ["Gift"]:
        hit_gift()
    else:
        raise NotImplementedError(RNG_CATEGORY)
    log('--- RNG 流程结束 ---')
    return True

def check_shiny():
    import cv2, numpy as np, time as _time
    from modules.pokemon_sprite import identify_pokemon as _identify, detect_gba_area, SPRITE_NATIVE
    log('Identifying...')

    for _ in range(20):
        if search_label('3代野怪血条', 90):
            break
        sleep(0.5)
    else:
        return False, None

    candidates = get_encounter_species_list(RNG_LOCATION, RNG_CATEGORY)
    if not candidates:
        raise RuntimeError(f'Empty encounter list for {RNG_LOCATION}/{RNG_CATEGORY}')

    frame = get_frame()
    if frame is None:
        raise RuntimeError('采集卡未就绪')

    species_id, score, is_shiny, fx_match, fy_match = _identify(frame, candidates=candidates, threshold=0.0)

    gx, gy, scale = detect_gba_area(frame)
    spx = int(SPRITE_NATIVE * scale)
    sx_roi = gx + int(140 * scale)
    sy_roi = gy
    sw_roi = int(72 * scale)
    sh_roi = int(100 * scale)

    if species_id is None or score < 0.95:
        ts = _time.strftime('%Y%m%d_%H%M%S')
        os.makedirs('debug_label', exist_ok=True)
        cv2.imencode('.png', frame)[1].tofile(f'debug_label/{ts}.png')
        log(f'identification failed (score={score:.3f})')
        raise RuntimeError(f'宝可梦识别失败 (最高匹配度={score:.3f})')

    pkm_en = get_species_en_name(get_species_zh_name(species_id))
    log(f'match: {pkm_en} (#{species_id}) score={score:.3f} {"SHINY" if is_shiny else "normal"}')

    dbg = frame.copy()
    cv2.rectangle(dbg, (sx_roi, sy_roi), (sx_roi+sw_roi, sy_roi+sh_roi), (255,255,0), 2)
    cv2.rectangle(dbg, (fx_match, fy_match), (fx_match+spx, fy_match+spx), (0,255,0), 3)
    cv2.putText(dbg, f'{pkm_en} score={score:.3f}', (sx_roi, sy_roi-5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
    os.makedirs('debug_label', exist_ok=True)
    safe_name = pkm_en.replace(' ', '_').replace("'", "")
    cv2.imencode('.png', dbg)[1].tofile(f'debug_label/{safe_name}.png')

    return is_shiny, pkm_en

# ---------- 普通捕获 (野外模式) ----------
def catch_with_ball():
    log('尝试捕获...')
    for _ in range(30):
        press('B'); sleep(0.5); press('RIGHT'); sleep(0.5)
        press('UP'); sleep(0.5)
        if search_label('3代关键词Bag', 90): break
    else:
        log('无法打开背包'); return False

    for i in range(50):
        sleep(2.0); press('A')
        for _ in range(5):
            press('RIGHT'); sleep(0.5)
            if search_label('3代关键词PokeBalls', 95): break
        for _ in range(5):
            if search_label('3代关键词UltraBall选中', 98): break
            press('DOWN'); sleep(0.5)
        for _ in range(10):
            press('A'); sleep(0.5)
            if search_label('3代野怪血条', 90): break
        else:
            log('血条异常退出'); return False
        for _ in range(60):
            press('B'); sleep(1.0)
            if search_label('3代关键词Bag', 90): break
            if search_label('3代关键词Gotcha', 90): return True
        else:
            log('界面异常退出'); return False
    return False

# ---------- OCR 宝可梦信息 ----------
LOG_DIR = None

def init_log_dir():
    global LOG_DIR
    ts = time.strftime('%Y%m%d_%H%M%S')
    d = f'rng_logs/{ts}_{POKEMON_SPECIES}'
    os.makedirs(d, exist_ok=True)
    LOG_DIR = d
    log(f'新建日志目录: {d}')
    shutil.copy(__file__, f'{d}/{os.path.basename(__file__)}')
    return d

# ---------- 保存 & 反查校准 ----------
def save_ocr(ocr_result, attempt, pokemon, candy_num=None):
    if LOG_DIR is None:
        init_log_dir()
    entry = {
        'attempt': attempt,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'pokemon': pokemon,
        'ocr_result': ocr_result,
    }
    if ocr_result["screen"] == "ELEVATED":
        assert candy_num is not None
        fname = f'{LOG_DIR}/{attempt:04d}_{ocr_result["screen"]}_{candy_num:02d}.json'
    else:
        fname = f'{LOG_DIR}/{attempt:04d}_{ocr_result["screen"]}.json'
    with open(fname, 'w', encoding='utf-8') as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)

# ---------- calculate_n_combos ----------
def calculate_n_combos(obs_list, pokemon):
    """pokemon: 宝可梦英文名（如 'Tentacool'）"""
    base_stats = get_personal(get_species_id(pokemon))["stats"]
    iv_range = _obs_to_iv_range(obs_list, base_stats)
    if iv_range is None:
        return 0
    lo, hi = iv_range
    return _n_combos(lo, hi)

def run_calibration():
    global SEED_BIAS, ADVANCES_BIAS
    global SEED_UNBIASED, SEED_MS
    global ADVANCES_UNBIASED, ADVANCES_MS_TV, ADVANCES_MS_NORMAL
    global valid_calibration_attempts, calibration_start_count

    if LOG_DIR is None: return
    files = sorted(glob.glob(f'{LOG_DIR}/*.json'))
    if len(files) < 1: return

    seed_bias, adv_bias = calibrate(
        seed_hex=SEED_HEX,
        seed_time=SEED,
        advances=ADVANCES,
        trainer_id=TRAINER_ID,
        secret_id=SECRET_ID,
        game_settings=GAME_SETTINGS,
        game=GAME_VERSION,
        method=RNG_METHOD,
        location=RNG_LOCATION,
        category=RNG_CATEGORY,
        log_dir=LOG_DIR,
    )

    if seed_bias is not None:
        SEED_BIAS += seed_bias
        ADVANCES_BIAS += adv_bias
        SEED_UNBIASED = SEED - SEED_BIAS
        SEED_MS = int(SEED_UNBIASED / FPS_SEED * 1000)
        ADVANCES_UNBIASED = ADVANCES - ADVANCES_BIAS
        ADVANCES_MS_TV = (ADVANCES_UNBIASED - ADVANCES_NORMAL) * 8 // FPS_TV * 125
        ADVANCES_MS_NORMAL = int((ADVANCES_UNBIASED - ADVANCES_MS_TV / 1000 * FPS_TV) / FPS_NORMAL * 1000)
        log(f'校准: {seed_bias=:+d} {adv_bias=:+d}')
        log(f'Seed={SEED} Advances={ADVANCES}')
        log(f'SeedBias={SEED_BIAS} AdvancesBias={ADVANCES_BIAS}')
        log(f'Seed takes {SEED_MS}ms | TV takes {ADVANCES_MS_TV}ms | Normal takes {ADVANCES_MS_NORMAL}ms')
        # 重置计数器
        valid_calibration_attempts = 0
        calibration_start_count = None
        init_log_dir()
    else:
        log('校准失败 (数据不足)')


# ---------- 微调记录 ----------
def record_for_finetune(attempt, pokemon):
    global valid_calibration_attempts, calibration_start_count

    if LOG_DIR is None:
        init_log_dir()
        calibration_start_count = attempt

    sleep(1.0)
    ocr_caught_info = ocr_pokemon()
    assert ocr_caught_info.get('screen') == "CAUGHT_INFO"
    nature = ocr_caught_info.get('nature')
    
    gender = 'male' if search_label('3代性别符号♂', 98) else 'female' if search_label('3代性别符号♀', 98) else 'unknown'
    ocr_caught_info['gender'] = gender

    save_ocr(ocr_caught_info, attempt, pokemon)

    sleep(0.5)
    press('RIGHT'); sleep(1.0)
    ocr_caught_iv = ocr_pokemon()
    ocr_caught_iv['gender'] = gender
    assert ocr_caught_iv.get('screen') == "CAUGHT_IV"
    save_ocr(ocr_caught_iv, attempt, pokemon)
    sleep(0.5)

    # 收集观测列表
    obs_list = []
    def _make_obs(ocr, nature):
        return IVsObservation(
            nature=nature, level=ocr['level'],
            hp=ocr['hp'], attack=ocr['attack'], defense=ocr['defense'],
            sp_attack=ocr['sp_atk'], sp_defense=ocr['sp_def'], speed=ocr['speed'],
        )
    obs_list.append(_make_obs(ocr_caught_iv, nature))

    # 喂糖循环 - 使用超参数 MAX_CANDIES
    for i in range(MAX_CANDIES):
        if i == 0:
            for _ in range(10):
                press('B'); sleep(0.5); press('B'); sleep(0.5)
                press('X'); sleep(1.0)
                if search_label('3代关键词POKeMON', 95): break
            for _ in range(20):
                if search_label('3代关键词BAG选中', 97): break
                press('DOWN'); sleep(0.5)
            sleep(1.0); press('A')
            for _ in range(5):
                press('LEFT'); sleep(0.5)
                if search_label('3代关键词Items', 95): break

            for _ in range(30):
                if search_label('3代神奇糖果', 95): break
                press('DOWN'); sleep(0.5)
            else:
                # TODO 增加意外情况截图记录
                break

        sleep(1.0); press('A'); sleep(1.0); press('A'); sleep(3.0)
        if i == 0:
            press('UP'); sleep(1.0); press('UP'); sleep(1.0)
        press('A'); sleep(3.0)

        for _ in range(10):
            press('B'); sleep(1.0)
            if search_label('3代升级能力值', 97):
                press('B'); sleep(0.5)
                ocr_elevated = ocr_pokemon()
                break
        else:
            # TODO 增加意外情况截图记录
            break

        assert ocr_elevated.get('screen') == "ELEVATED"
        save_ocr(ocr_elevated, attempt, pokemon, candy_num=i+1)

        obs_list.append(_make_obs(ocr_elevated, nature))
        current_n_combos = calculate_n_combos(obs_list, pokemon)
        log(f' {len(obs_list)} IVs observations | {current_n_combos} IVs combos')
        if current_n_combos <= PRECICASE_COMBOS:
            valid_calibration_attempts += 1
            break

        for _ in range(30):
            press('B'); sleep(0.5)
            if search_label('3代神奇糖果', 95): break
            if search_label('3代技能替换', 95): press('B'); sleep(1.0); press('A'); sleep(0.5)
        else:
            # TODO 增加意外情况截图记录
            break

    log(f' {attempt} attempts | {valid_calibration_attempts} precise observations')
    if valid_calibration_attempts >= FINETUNE_PER_PRECICASE:
        run_calibration()

def check_last_pokemon():
    log('查看末位精灵...')
    for _ in range(20):
        press('B'); sleep(0.5); press('B'); sleep(0.5)
        press('X'); sleep(1.0)
        if search_label('3代关键词POKeMON', 95): break
    for _ in range(20):
        if search_label('3代关键词POKeMON选中', 97): break
        press('DOWN'); sleep(0.5)
    sleep(2.0); press('A'); sleep(1.8)
    press('UP'); sleep(1.0); press('UP'); sleep(1.0)
    for _ in range(100):
        press('A'); sleep(1.0)
        if search_label('3代精灵球', 85): break

# ---------- 重启游戏 ----------
def restart():
    log('重启游戏...')
    for _ in range(30):
        press('HOME'); sleep(3.0)
        if search_label('NS主页满电量', 90): break
    press('X'); sleep(1.0)
    for _ in range(10):
        press('A'); sleep(3.0)
        if search_label('NS主页选择玩家', 90): break

# ---------- 主循环 ----------
def main():
    log(f"{GAME_SETTINGS=}")
    log(f'Seed={SEED} Advances={ADVANCES}')
    log(f'SeedBias={SEED_BIAS} AdvancesBias={ADVANCES_BIAS}')
    log(f'Seed takes {SEED_MS}ms | TV takes {ADVANCES_MS_TV}ms | Normal takes {ADVANCES_MS_NORMAL}ms')
    count = 0
    while is_running():
        count += 1
        log(f'========== 乱数尝试第 {count} 次 ==========')

        hit()

        if RNG_CATEGORY in ["Grass", "Surfing", "SuperRod"]:
            is_shiny, pokemon_en = check_shiny()
            if is_shiny:
                log('Shiny found!'); break
            if pokemon_en:
                caught = catch_with_ball()
                if caught:
                    check_last_pokemon()
                    record_for_finetune(count, pokemon_en)
        elif RNG_CATEGORY == "Gift":
            check_last_pokemon()
            if search_label('3代闪光', 80):
                log('Shiny found!'); break
            else:
                record_for_finetune(count, POKEMON_SPECIES)
        else:
            raise NotImplementedError(RNG_CATEGORY)

        restart()

    press('CAPTURE', 3000)


if __name__ == '__main__':
    run_script(main)
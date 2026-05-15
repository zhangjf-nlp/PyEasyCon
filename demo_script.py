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

from gui import press, hold, release, capture, wait, log, search_label, is_running, ocr_pokemon, get_frame, ocr_custom, identify_pokemon, ocr_name
from gui import run_script

from calibration import calibrate, _obs_to_iv_range, _n_combos
from modules.tenlines.tenlines_utils import ENCOUNTER_TYPE_MAP, IVsObservation, GameSettings, get_species_id, get_personal, get_seed_time, get_species_zh_name, get_species_en_name, get_encounter_species_list, get_species_name


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
FINETUNE_PRECISE_COMBOS = 64   # 符合precision条件的n_combos上限
FINETUNE_MIN_VALID = 3         # 收集多少个符合条件的案例后进行校准
CANDY_FEED_TIMES = 10          # 喂神奇糖果的次数

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
    assert search_label('3代关键词KeyItems', 95)
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

def get_expected_zh_names():
    """根据当前 RNG location 获取预期宝可梦的中文名列表"""
    species_list = get_encounter_species_list(RNG_LOCATION, RNG_CATEGORY)
    return [get_species_zh_name(s) for s in species_list]


# ---------- 精灵匹配识别配置 ----------
# 搜索区域硬编码在 pokemon_sprite 中 (GBA x=144, y=0~100)

# 首次匹配跟踪（持久化到磁盘）
_SEEN_FILE = 'rng_logs/_seen_species.json'
def _load_seen():
    if os.path.exists(_SEEN_FILE):
        with open(_SEEN_FILE) as f:
            return set(json.load(f))
    return set()
def _save_seen(s):
    os.makedirs(os.path.dirname(_SEEN_FILE), exist_ok=True)
    with open(_SEEN_FILE, 'w') as f:
        json.dump(sorted(s), f)
_seen_species = _load_seen()

# ---------- 闪光检测 & 自动标签制作 ----------
SHINY_THRESHOLD = 90
from modules.pokemon_ocr import ocr_pokemon_name

# 参考现有"3代普通xxx"标签的识别范围（中位数）
_AUTO_LABEL_RANGE = (1178, 208, 277, 259)       # RangeX, RangeY, RangeWidth, RangeHeight
_AUTO_LABEL_TARGET = (14, 15, 246, 235)          # Target offset from Range (dx, dy, w, h)


def _make_label(zh_name, frame):
    """制作单个标签并保存到 labels/ 目录，返回是否成功"""
    import cv2, base64

    RX, RY, RW, RH = _AUTO_LABEL_RANGE
    DX, DY, TW, TH = _AUTO_LABEL_TARGET
    tx, ty = RX + DX, RY + DY

    h, w = frame.shape[:2]
    if ty + TH > h or tx + TW > w:
        log(f'[label] 裁剪越界: ({tx},{ty},{TW},{TH}) vs ({w}x{h})')
        return False

    target_roi = frame[ty:ty + TH, tx:tx + TW]
    label_name = f'3代普通{zh_name}'
    label_path = os.path.join('labels', f'{label_name}.IL')

    _, buf = cv2.imencode('.png', target_roi)
    img_b64 = base64.b64encode(buf).decode()

    label_data = {
        "name": label_name,
        "searchMethod": 1,
        "ImgBase64": img_b64,
        "RangeX": RX, "RangeY": RY, "RangeWidth": RW, "RangeHeight": RH,
        "TargetX": tx, "TargetY": ty, "TargetWidth": TW, "TargetHeight": TH,
    }
    with open(label_path, 'w', encoding='utf-8') as f:
        json.dump(label_data, f, indent=2)

    for _ in range(5):
        deg = search_label(label_name, -1)
        if deg >= 99:
            log(f'[label] ✓ {label_name} ({deg:.0f}%)')
            return True
        sleep(0.2)

    log(f'[label] ✗ {label_name} 验证未达99%，请手动检查')
    return False



def _try_auto_label(missing_set):
    """识别当前宝可梦名并为 missing_set 制作标签"""
    frame = get_frame()
    if frame is None:
        return

    # 构建备选列表
    expected_zh = get_expected_zh_names()
    candidates = [
        f"{zh}({get_species_en_name(zh)})"
        for zh in sorted(set(expected_zh))
        if get_species_en_name(zh) != zh
    ]
    en_name = ocr_pokemon_name(frame, candidates)
    if en_name is None or en_name.upper() == 'NONE':
        log('[label] GLM 未识别到已知宝可梦')
        return

    log(f'[label] OCR: {en_name}')

    try:
        sid = get_species_id(en_name)
    except ValueError:
        log(f'[label] 无法解析: {en_name}')
        return

    zh_name = get_species_zh_name(sid)
    if zh_name not in missing_set:
        log(f'[label] {zh_name} 不在缺标签列表中')
        return

    _make_label(zh_name, frame)


def check_shiny():
    """
    检测当前遇到的是否闪光。
    主识别：GBA 精灵图全局最佳匹配（normal + shiny），始终取最高分。
    双重验证：首次匹配到某宝可梦时调用 OCR 确认。
    返回 (is_shiny: bool, pokemon_en: str | None)
    异常：检测不到血条/候选为空时抛出 RuntimeError。
    """
    import cv2, hashlib, time as _time
    log('Identifying...')

    # 1. 检测野怪血条
    for _ in range(20):
        if search_label('3代野怪血条', 90):
            break
        sleep(0.5)
    else:
        return False, None

    # 2. 获取候选
    candidates = get_encounter_species_list(RNG_LOCATION, RNG_CATEGORY)
    if not candidates:
        raise RuntimeError(f'Empty encounter list for {RNG_LOCATION}/{RNG_CATEGORY}')
    log(f'  candidates: {[get_species_en_name(get_species_zh_name(c)) for c in candidates]}')

    # 3. 全局最佳匹配
    species_id, score, is_shiny = identify_pokemon(
        candidates=candidates,
        threshold=0.0,
    )

    if species_id is None or score < 0.3:
        # 保存调试截图
        frame = get_frame()
        if frame is not None:
            try:
                from modules.pokemon_sprite import detect_gba_area
                gx, gy, scale = detect_gba_area(frame)
                sx = gx + int(140 * scale)
                sy = gy
                sw = int(72 * scale)
                sh = int(100 * scale)
                ts = _time.strftime('%Y%m%d_%H%M%S')
                h = hashlib.md5(f'{ts}{score}'.encode()).hexdigest()[:6]
                dbg = frame.copy()
                cv2.rectangle(dbg, (gx, gy), (gx+int(240*scale), gy+int(160*scale)), (255,255,0), 2)
                cv2.rectangle(dbg, (sx, sy), (sx+sw, sy+sh), (0,0,255), 2)
                os.makedirs('debug_label', exist_ok=True)
                cv2.imencode('.png', dbg)[1].tofile(f'debug_label/identify_fail_{ts}_{h}.png')
                log(f'  debug frame saved (score={score:.3f})')
            except Exception:
                pass
        log(f'  identification failed (score={score:.3f}), assuming shiny')
        return False, None

    pkm_en = get_species_en_name(get_species_zh_name(species_id))
    log(f'  match: {pkm_en} (#{species_id}) score={score:.3f} {"SHINY" if is_shiny else "normal"}')

    # 4. 双重验证：首次匹配到此宝可梦时调用 OCR 确认
    global _seen_species
    if species_id not in _seen_species:
        log(f'  first encounter of #{species_id}, OCR verifying...')
        ocr_candidates = [
            f"{get_species_zh_name(c)}({get_species_en_name(get_species_zh_name(c))})"
            for c in candidates
        ]
        ocr_en = ocr_name(candidates=ocr_candidates)
        if ocr_en:
            try:
                ocr_sid = get_species_id(ocr_en)
                if ocr_sid != species_id:
                    log(f'  OCR mismatch: appearance={pkm_en} OCR={get_species_en_name(get_species_zh_name(ocr_sid))}')
                    log(f'  using OCR result')
                    species_id = ocr_sid
                    pkm_en = get_species_en_name(get_species_zh_name(ocr_sid))
                    is_shiny = False
                else:
                    log(f'  OCR confirmed: {pkm_en}')
            except ValueError:
                log(f'  OCR result unresolvable: {ocr_en}')
        else:
            log(f'  OCR unavailable, trusting appearance match')
    _seen_species.add(species_id)
    _save_seen(_seen_species)

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

    # 喂糖循环 - 使用超参数 CANDY_FEED_TIMES
    for i in range(CANDY_FEED_TIMES):
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
        if current_n_combos <= FINETUNE_PRECISE_COMBOS:
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
    if valid_calibration_attempts >= FINETUNE_MIN_VALID:
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
                log(f'  current: {pokemon_en}')
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
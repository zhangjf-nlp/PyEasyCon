"""
Pokemon Sprite Matching Module
基于 appearance/ 精灵图 + OpenCV 模板匹配识别画面中的宝可梦。
搜索区域硬编码：GBA x=144(固定), y=0~100(扫描), 精灵宽 72px.
"""
import os, cv2, numpy as np
from typing import Optional, List, Tuple, Dict

def imread_func(path, flags=cv2.IMREAD_UNCHANGED):
    try:
        with open(path, "rb") as f:
            return cv2.imdecode(np.frombuffer(f.read(), np.uint8), flags)
    except Exception:
        return None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORMAL_DIR = os.path.join(BASE_DIR, "assets", "sprites", "normal")
SHINY_DIR = os.path.join(BASE_DIR, "assets", "sprites", "shiny")
GBA_W, GBA_H = 240, 160
SPRITE_NATIVE = 64

_sprite_cache: Dict[str, np.ndarray] = {}
_gba_cache: Dict[tuple, tuple] = {}


def detect_gba_area(frame: np.ndarray) -> Tuple[int, int, float]:
    key = frame.shape[:2]
    if key in _gba_cache:
        return _gba_cache[key]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = gray > 15
    rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
    if not np.any(rows) or not np.any(cols):
        return (0, 0, 1.0)
    y1, y2 = np.where(rows)[0][[0, -1]]
    x1, x2 = np.where(cols)[0][[0, -1]]
    scale = ((x2 - x1 + 1) / GBA_W + (y2 - y1 + 1) / GBA_H) / 2
    result = (int(x1), int(y1), scale)
    _gba_cache[key] = result
    return result


def get_sprite_paths(species_id: int) -> List[Tuple[str, str, str]]:
    """Return all sprite files for a species, including multi-form variants.
    Each entry: (display_name, normal_path, shiny_path)."""
    result = []
    sid = str(species_id)
    # check default form first
    default_n = os.path.join(NORMAL_DIR, f"{sid}.png")
    default_s = os.path.join(SHINY_DIR, f"{sid}.png")
    if os.path.exists(default_n):
        result.append((sid, default_n, default_s))
    # scan for suffixed forms: {id}-{form}.png
    for fname in sorted(os.listdir(NORMAL_DIR)):
        if not fname.endswith('.png'):
            continue
        if not fname.startswith(sid + '-'):
            continue
        # e.g. "201-A.png" -> display_name "201-A"
        display_name = fname[:-4]
        result.append((
            display_name,
            os.path.join(NORMAL_DIR, fname),
            os.path.join(SHINY_DIR, fname),
        ))
    return result


def load_sprite_func(path: str) -> Optional[np.ndarray]:
    if path in _sprite_cache:
        return _sprite_cache[path].copy()
    if not os.path.exists(path):
        return None
    img = imread_func(path)
    if img is None:
        return None
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    _sprite_cache[path] = img.copy()
    return img


def match_one(search_frame, sprite_bgra, sprite_px, fh, fw):
    bgr, alpha = sprite_bgra[:,:,:3], sprite_bgra[:,:,3]
    mask = (alpha > 128).astype(np.uint8) * 255
    tpl = cv2.resize(bgr, (sprite_px, sprite_px), interpolation=cv2.INTER_NEAREST)
    msk = cv2.resize(mask, (sprite_px, sprite_px), interpolation=cv2.INTER_NEAREST)
    if np.count_nonzero(msk) < 10 or sprite_px > fh or sprite_px > fw:
        return 0.0, (0, 0)
    result = cv2.matchTemplate(search_frame, tpl, cv2.TM_SQDIFF_NORMED, mask=msk)
    min_val, _, min_loc, _ = cv2.minMaxLoc(result)
    return max(0.0, 1.0 - float(min_val)), (min_loc[0], min_loc[1])


def score_species(frame, species_id, shiny, gba):
    gx, gy, scale = gba
    spx = int(SPRITE_NATIVE * scale)
    if spx < 8:
        return 0.0, (0, 0)
    sx = gx + int(140 * scale)
    sw = int(72 * scale)
    sh = int(100 * scale)
    search = frame[gy:gy+sh, sx:sx+sw]
    fh, fw = search.shape[:2]
    best, best_pos = 0.0, (0, 0)
    for _, np_path, sp_path in get_sprite_paths(species_id):
        sprite = load_sprite_func(sp_path if shiny else np_path)
        if sprite is None:
            continue
        s, (mx, my) = match_one(search, sprite, spx, fh, fw)
        if s > best:
            best = s
            best_pos = (sx + mx, gy + my)
    return best, best_pos


def identify_pokemon(frame: np.ndarray,
                     candidates: Optional[List[int]] = None,
                     threshold: float = 0.0) -> Tuple[Optional[int], float, bool, int, int]:
    if candidates is None:
        candidates = sorted(set(
            int(f.split('.')[0].split('-')[0])
            for f in os.listdir(NORMAL_DIR) if f.endswith('.png')
        ))

    gba = detect_gba_area(frame)
    for sid in candidates:
        for _, np_path, sp_path in get_sprite_paths(sid):
            load_sprite_func(np_path)
            load_sprite_func(sp_path)

    best_sid, best_score, best_shiny = None, 0.0, False
    best_mx, best_my = 0, 0
    for sid in candidates:
        ns, (nmx, nmy) = score_species(frame, sid, False, gba)
        if ns > best_score:
            best_score, best_sid, best_shiny = ns, sid, False
            best_mx, best_my = nmx, nmy
        ss, (smx, smy) = score_species(frame, sid, True, gba)
        if ss > best_score:
            best_score, best_sid, best_shiny = ss, sid, True
            best_mx, best_my = smx, smy

    if best_score < threshold:
        return None, best_score, False, 0, 0
    return best_sid, best_score, best_shiny, best_mx, best_my


def preload_sprites(species_ids: List[int]):
    for sid in species_ids:
        for _, np_path, sp_path in get_sprite_paths(sid):
            load_sprite_func(np_path)
            load_sprite_func(sp_path)

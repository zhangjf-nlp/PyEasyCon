"""
Convert GBA sprites to .IL labels for EasyCon MaskedSqDiffNormed (searchMethod=14).
Saves full 64x64 sprite upscaled as RGBA PNG — alpha channel becomes the mask,
excluding transparent background from matching.

Configuration:
  SCALE       - GBA -> NS frame scale (default 6.5)
  GBA_X, GBA_Y - GBA area offset on 1920x1080 capture
  ROI_GBA_*    - search region in GBA coords
  SEARCH_METHOD - 14 = MaskedSqDiffNormed
  OUT_DIR      - output directory
"""
import sys, os, cv2, json, base64, numpy as np
sys.path.insert(0, '.')
from modules.pokemon_sprite import _load_sprite, _get_sprite_paths, NORMAL_DIR

SCALE = 6.5
GBA_X, GBA_Y = 180, 5
ROI_GBA_X, ROI_GBA_W = 140, 72
ROI_GBA_Y, ROI_GBA_H = 0, 100
SEARCH_METHOD = 14
OUT_DIR = 'ImgLabel-FRLG'
SPRITE_PX = int(64 * SCALE)

os.makedirs(OUT_DIR, exist_ok=True)
from modules.tenlines.tenlines_utils import get_species_en_name, get_species_zh_name

all_ids = sorted(set(
    int(f.split('.')[0].split('-')[0])
    for f in os.listdir(NORMAL_DIR) if f.endswith('.png')
))

ok = 0
for sid in all_ids:
    en = get_species_en_name(get_species_zh_name(sid))
    for shiny in [False, True]:
        label_name = f'frlg_{sid}_{en}_s' if shiny else f'frlg_{sid}_{en}'
        label_path = os.path.join(OUT_DIR, f'{label_name}.IL')

        sprite = None
        for _, np_path, sp_path in _get_sprite_paths(sid):
            s = _load_sprite(sp_path if shiny else np_path)
            if s is not None:
                sprite = s
                break
        if sprite is None:
            continue

        # Full sprite upscaled to NS resolution, RGBA (alpha = mask)
        bgr = cv2.resize(sprite[:,:,:3], (SPRITE_PX, SPRITE_PX), interpolation=cv2.INTER_NEAREST)
        alpha = cv2.resize(sprite[:,:,3], (SPRITE_PX, SPRITE_PX), interpolation=cv2.INTER_NEAREST)
        rgba = np.dstack([bgr, alpha])

        _, buf = cv2.imencode('.png', rgba, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        img_b64 = base64.b64encode(buf).decode()

        rx = GBA_X + int(ROI_GBA_X * SCALE)
        ry = GBA_Y + int(ROI_GBA_Y * SCALE)
        rw = int(ROI_GBA_W * SCALE)
        rh = int(ROI_GBA_H * SCALE)

        tx = rx + int(4 * SCALE)
        ty = ry
        tw = SPRITE_PX
        th = SPRITE_PX

        label_data = {
            "name": label_name,
            "searchMethod": SEARCH_METHOD,
            "ImgBase64": img_b64,
            "RangeX": rx, "RangeY": ry, "RangeWidth": rw, "RangeHeight": rh,
            "TargetX": tx, "TargetY": ty, "TargetWidth": tw, "TargetHeight": th,
        }
        with open(label_path, 'w', encoding='utf-8') as f:
            json.dump(label_data, f, indent=2)
        ok += 1

print(f"Done: {ok} labels -> {OUT_DIR}/ (searchMethod={SEARCH_METHOD} MaskedSqDiffNormed)")

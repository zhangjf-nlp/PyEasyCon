"""
Convert GBA sprites to .IL labels for EasyCon MaskedSqDiffNormed (searchMethod=14).
Saves full 64x64 sprite upscaled as RGBA PNG — alpha channel becomes the mask,
excluding transparent background from matching.

Multi-form species produce per-form labels:
  frlg_{id}_{name}.IL / frlg_{id}_{name}_s.IL          (default form)
  frlg_{id}_{name}_{form}.IL / frlg_{id}_{name}_{form}_s.IL  (other forms)

Configuration:
  SCALE       - GBA -> NS frame scale (default 6.5)
  GBA_X, GBA_Y - GBA area offset on 1920x1080 capture
  ROI_GBA_*    - search region in GBA coords
  SEARCH_METHOD - 14 = MaskedSqDiffNormed
  OUT_DIR      - output directory
"""
import sys, os, cv2, json, base64, numpy as np
sys.path.insert(0, '.')
from vision.sprite import load_sprite_func, NORMAL_DIR, SHINY_DIR

SCALE = 6.5
GBA_X, GBA_Y = 180, 5
ROI_GBA_X, ROI_GBA_W = 140, 72
ROI_GBA_Y, ROI_GBA_H = 0, 100
SEARCH_METHOD = 14
OUT_DIR = 'assets/sprite_labels'
SPRITE_PX = int(64 * SCALE)

os.makedirs(OUT_DIR, exist_ok=True)
from rng.tenlines_utils import get_species_en_name, get_species_zh_name

# collect all sprite files (including multi-form) from normal/
all_files = sorted(f for f in os.listdir(NORMAL_DIR) if f.endswith('.png'))

ok = 0
for fname in all_files:
    name_no_ext = fname[:-4]  # e.g. "201-A", "351", "386-atk"
    # parse species id and optional form suffix
    if '-' in name_no_ext:
        # could be "201-A" or "351-rainy" or "386-atk"
        # species id is digits before the first '-'
        parts = name_no_ext.split('-', 1)
        sid_str, form = parts[0], parts[1]
    else:
        sid_str, form = name_no_ext, ""
    sid = int(sid_str)

    en = get_species_en_name(get_species_zh_name(sid))

    for shiny in [False, True]:
        # label naming
        if form:
            label_name = f'frlg_{sid}_{en}_{form}_s' if shiny else f'frlg_{sid}_{en}_{form}'
        else:
            label_name = f'frlg_{sid}_{en}_s' if shiny else f'frlg_{sid}_{en}'
        label_path = os.path.join(OUT_DIR, f'{label_name}.IL')

        sprite_path = os.path.join(SHINY_DIR if shiny else NORMAL_DIR, fname)
        sprite = load_sprite_func(sprite_path)
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

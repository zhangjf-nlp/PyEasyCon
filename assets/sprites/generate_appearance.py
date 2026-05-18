"""
Build normal/ and shiny/ sprites from resources/.
Special cases:
  #351 Castform: generates 351.png / 351-normal.png / 351-rainy.png / 351-snowy.png / 351-sunny.png
  #386 Deoxys: keeps normal form only as 386.png
"""
import os

from PIL import Image

BASE     = os.path.dirname(__file__)
RES_DIR  = os.path.join(BASE, "resources")
NORM_DIR = os.path.join(BASE, "normal")
SHIN_DIR = os.path.join(BASE, "shiny")
os.makedirs(NORM_DIR, exist_ok=True)
os.makedirs(SHIN_DIR, exist_ok=True)

def parse_pal(path):
    with open(path) as f:
        lines = f.read().strip().splitlines()
    return [tuple(int(x) for x in l.strip().split()) for l in lines[3:] if len(l.strip().split()) == 3]

def apply_palette(img_p, colors):
    pal_flat = []
    for r, g, b in colors:
        pal_flat.extend([r, g, b])
    pal_flat.extend([0] * (768 - len(pal_flat)))
    img_p.putpalette(pal_flat)
    rgba = img_p.convert("RGBA")
    bg = colors[0]
    px = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = px[x, y]
            if (r, g, b) == bg or (r == 255 and g == 0 and b == 255):
                px[x, y] = (0, 0, 0, 0)
    return rgba

def build_one(img_path, pal_n_path, pal_s_path, out_name):
    nc  = parse_pal(pal_n_path)
    sc  = parse_pal(pal_s_path)
    img = Image.open(img_path)
    if img.mode != "P":
        img = img.convert("P", palette=Image.ADAPTIVE, colors=16)
    apply_palette(img.copy(), nc).save(os.path.join(NORM_DIR, out_name))
    apply_palette(img.copy(), sc).save(os.path.join(SHIN_DIR, out_name))

ok, skip, fail = 0, 0, 0

for nat_id in range(1, 387):
    front_path  = os.path.join(RES_DIR, f"{nat_id}.png")
    normal_path = os.path.join(RES_DIR, f"{nat_id}_normal.pal")
    shiny_path  = os.path.join(RES_DIR, f"{nat_id}_shiny.pal")
    if not all(os.path.exists(p) for p in (front_path, normal_path, shiny_path)):
        continue

    try:
        if nat_id == 351:
            forms = ["normal", "rainy", "snowy", "sunny"]
            for form in forms:
                prefix = "351" if form == "normal" else f"351-{form}"
                img_p  = os.path.join(RES_DIR, f"351.png" if form == "normal" else f"351-{form}.png")
                pal_n  = os.path.join(RES_DIR, f"351_normal.pal" if form == "normal" else f"351-{form}_normal.pal")
                pal_s  = os.path.join(RES_DIR, f"351_shiny.pal"  if form == "normal" else f"351-{form}_shiny.pal")
                out_n  = os.path.join(NORM_DIR, f"{prefix}.png")
                out_s  = os.path.join(SHIN_DIR, f"{prefix}.png")
                if os.path.exists(out_n) and os.path.exists(out_s):
                    skip += 1
                    continue
                build_one(img_p, pal_n, pal_s, f"{prefix}.png")
                ok += 1
            continue

        if nat_id == 386:
            img = Image.open(front_path)
            if img.mode != "P":
                img = img.convert("P", palette=Image.ADAPTIVE, colors=16)
            nc = parse_pal(normal_path)
            sc = parse_pal(shiny_path)
            if img.height == 128:
                img = img.crop((0, 0, 64, 64))
            out_n = os.path.join(NORM_DIR, "386.png")
            out_s = os.path.join(SHIN_DIR, "386.png")
            if not (os.path.exists(out_n) and os.path.exists(out_s)):
                apply_palette(img.copy(), nc).save(out_n)
                apply_palette(img.copy(), sc).save(out_s)
                ok += 1
            else:
                skip += 1
            continue

        out_n = os.path.join(NORM_DIR, f"{nat_id}.png")
        out_s = os.path.join(SHIN_DIR, f"{nat_id}.png")
        if os.path.exists(out_n) and os.path.exists(out_s):
            skip += 1
            continue
        build_one(front_path, normal_path, shiny_path, f"{nat_id}.png")
        ok += 1

    except Exception as e:
        fail += 1
        print(f"  [FAIL] #{nat_id:03d}: {e}")

print(f"Done: ok={ok} fail={fail} skip={skip}")
print(f"  normal/: {len(os.listdir(NORM_DIR))} files")
print(f"  shiny/ : {len(os.listdir(SHIN_DIR))} files")

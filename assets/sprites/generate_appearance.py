"""
Build normal/ and shiny/ sprites from resources/.
Multi-form species:
  #201 Unown:    scans 201-{A..Z,emark,qmark}.png with shared 201_normal.pal / 201_shiny.pal
  #351 Castform: scans 351.png (normal), 351-{rainy,snowy,sunny}.png with per-form palettes
  #386 Deoxys:   386.png (64x128) cropped to 386.png (top) / 386-atk.png (bottom),
                 386_def.png (64x128) cropped to 386-def.png (bottom),
                 all share 386_normal.pal / 386_shiny.pal
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


def get_form_sprite_paths(nat_id):
    """Yield (form_suffix, resource_png_path) for all forms of a species.
    form_suffix examples: '' (default), '-A', '-rainy', '-atk', etc."""
    # check for default form first
    default_png = os.path.join(RES_DIR, f"{nat_id}.png")
    if os.path.exists(default_png):
        yield "", default_png
    # scan for suffixed forms
    prefix = f"{nat_id}-"
    for fname in sorted(os.listdir(RES_DIR)):
        if fname.startswith(prefix) and fname.endswith(".png"):
            # e.g. "201-A.png" -> suffix "-A"
            suffix = "-" + fname[len(prefix):-4]
            yield suffix, os.path.join(RES_DIR, fname)


def find_palette(nat_id, suffix):
    """Find normal/shiny palette for a given species+form.
    Tries {id}{suffix}_normal.pal first, then falls back to {id}_normal.pal."""
    for pal_name in (f"{nat_id}{suffix}_normal.pal", f"{nat_id}_normal.pal"):
        pal_path = os.path.join(RES_DIR, pal_name)
        if os.path.exists(pal_path):
            return pal_path
    return None


# ---- scanning approach: iterate all PNGs in resources/ ----
ok, skip, fail = 0, 0, 0
processed = set()  # (species_id, form_suffix) to avoid duplicates

for nat_id in range(1, 387):
    # ---- deoxys special case: crop from 64x128 raw sprites ----
    if nat_id == 386:
        front_path = os.path.join(RES_DIR, "386.png")
        front_def_path = os.path.join(RES_DIR, "386_def.png")
        normal_pal = os.path.join(RES_DIR, "386_normal.pal")
        shiny_pal = os.path.join(RES_DIR, "386_shiny.pal")
        if not all(os.path.exists(p) for p in (front_path, normal_pal, shiny_pal)):
            continue

        try:
            nc = parse_pal(normal_pal)
            sc = parse_pal(shiny_pal)

            # 386.png (64x128): top 64x64 = normal, bottom 64x64 = attack
            img = Image.open(front_path)
            if img.mode != "P":
                img = img.convert("P", palette=Image.ADAPTIVE, colors=16)
            h = img.height
            if h == 128:
                img_norm = img.crop((0, 0, 64, 64))
                img_atk  = img.crop((0, 64, 64, 128))
            else:
                img_norm = img
                img_atk = None

            out_n = os.path.join(NORM_DIR, "386.png")
            out_s = os.path.join(SHIN_DIR, "386.png")
            if not (os.path.exists(out_n) and os.path.exists(out_s)):
                apply_palette(img_norm.copy(), nc).save(out_n)
                apply_palette(img_norm.copy(), sc).save(out_s)
                ok += 1
            else:
                skip += 1

            if img_atk is not None:
                out_atk_n = os.path.join(NORM_DIR, "386-atk.png")
                out_atk_s = os.path.join(SHIN_DIR, "386-atk.png")
                if not (os.path.exists(out_atk_n) and os.path.exists(out_atk_s)):
                    apply_palette(img_atk.copy(), nc).save(out_atk_n)
                    apply_palette(img_atk.copy(), sc).save(out_atk_s)
                    ok += 1
                else:
                    skip += 1

            # 386_def.png (64x128): bottom 64x64 = defense
            if os.path.exists(front_def_path):
                img_def = Image.open(front_def_path)
                if img_def.mode != "P":
                    img_def = img_def.convert("P", palette=Image.ADAPTIVE, colors=16)
                if img_def.height == 128:
                    img_def_crop = img_def.crop((0, 64, 64, 128))
                else:
                    img_def_crop = img_def

                out_def_n = os.path.join(NORM_DIR, "386-def.png")
                out_def_s = os.path.join(SHIN_DIR, "386-def.png")
                if not (os.path.exists(out_def_n) and os.path.exists(out_def_s)):
                    apply_palette(img_def_crop.copy(), nc).save(out_def_n)
                    apply_palette(img_def_crop.copy(), sc).save(out_def_s)
                    ok += 1
                else:
                    skip += 1
        except Exception as e:
            fail += 1
            print(f"  [FAIL] #386: {e}")
        continue

    # ---- generic multi-form handling ----
    for suffix, front_path in get_form_sprite_paths(nat_id):
        pal_n = find_palette(nat_id, suffix)
        if pal_n is None:
            continue
        pal_s = pal_n.replace("_normal.pal", "_shiny.pal")
        if not os.path.exists(pal_s):
            continue

        out_name = f"{nat_id}{suffix}.png"
        key = (nat_id, suffix)
        if key in processed:
            continue
        processed.add(key)

        out_n = os.path.join(NORM_DIR, out_name)
        out_s = os.path.join(SHIN_DIR, out_name)
        if os.path.exists(out_n) and os.path.exists(out_s):
            skip += 1
            continue

        try:
            build_one(front_path, pal_n, pal_s, out_name)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  [FAIL] #{nat_id}{suffix}: {e}")

print(f"Done: ok={ok} fail={fail} skip={skip}")
print(f"  normal/: {len(os.listdir(NORM_DIR))} files")
print(f"  shiny/ : {len(os.listdir(SHIN_DIR))} files")

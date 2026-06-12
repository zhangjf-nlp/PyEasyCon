"""
Download raw resources into assets/sprites/resources/:
  {id}.png       - pret/pokefirered front.png (4-bit colormap, raw)
  {id}_normal.pal
  {id}_shiny.pal
Supports multi-form species:
  #201 Unown:    {id}-{A..Z,emark,qmark}.png (shared palettes at unown/ level)
  #351 Castform: {id}.png / {id}-{rainy,snowy,sunny}.png (per-form palettes)
  #386 Deoxys:   {id}.png / {id}-{atk,def}.png (shared palettes, front.png cropped)
Uses PokeAPI national dex to map dex_id -> pokemon name -> pret directory name.
Skips existing files (re-runnable).
"""
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request

PRET_BASE = "https://raw.githubusercontent.com/pret/pokefirered/master/graphics/pokemon"
POKEDEX_1 = "https://pokeapi.co/api/v2/pokedex/1/?limit=400"
HEADERS   = {"User-Agent": "EasyCon-sprites-downloader/1.0"}

RES_DIR   = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "sprites", "resources")
os.makedirs(RES_DIR, exist_ok=True)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
        return r.read()

MANUAL_OVERRIDES = {
    "farfetch-d": "farfetchd",
    "mr-mime":    "mr_mime",
    "ho-oh":      "ho_oh",
    "mime-jr":    "mime_jr",
    "porygon-z":  "porygon_z",
}

# ---- multi-form species definitions ----
# unown:   unown/{pret_form}/front.png  (shared palettes at unown/ level)
# castform: castform/{pret_form}/front.png  (per-form palettes)
# deoxys:  deoxys/front.png (64x128, normal+attack), deoxys/front_def.png (64x128, normal+defense)
#          shared palettes at deoxys/ level; cropping done in generate_appearance

UNOWN_FORM_MAP = [
    ("a", "A"), ("b", "B"), ("c", "C"), ("d", "D"), ("e", "E"),
    ("f", "F"), ("g", "G"), ("h", "H"), ("i", "I"), ("j", "J"),
    ("k", "K"), ("l", "L"), ("m", "M"), ("n", "N"), ("o", "O"),
    ("p", "P"), ("q", "Q"), ("r", "R"), ("s", "S"), ("t", "T"),
    ("u", "U"), ("v", "V"), ("w", "W"), ("x", "X"), ("y", "Y"),
    ("z", "Z"), ("exclamation_mark", "emark"), ("question_mark", "qmark"),
]
CASTFORM_FORMS = [("normal", ""), ("rainy", "rainy"), ("snowy", "snowy"), ("sunny", "sunny")]

def api_to_pret_dir(api_name):
    if api_name in MANUAL_OVERRIDES:
        return MANUAL_OVERRIDES[api_name]
    return re.sub(r"[^a-z0-9_]", "", api_name.lower().replace("-", "_"))

# ---------- id2dir ----------
CACHE = os.path.join(RES_DIR, "id2dir.json")
if os.path.exists(CACHE):
    with open(CACHE) as f:
        id2dir = {int(k): v for k, v in json.load(f).items()}
    print(f"id2dir loaded from cache: {len(id2dir)} entries")
else:
    print("Fetching national dex from PokeAPI ...")
    for attempt in range(3):
        try:
            entries = json.loads(fetch(POKEDEX_1))["pokemon_entries"]
            break
        except Exception as e:
            print(f"  retry {attempt+1}: {e}")
            time.sleep(3)
    id2dir = {}
    for e in entries:
        nat_id = e["entry_number"]
        if nat_id > 386:
            continue
        api_name = e["pokemon_species"]["name"]
        id2dir[nat_id] = api_to_pret_dir(api_name)
    with open(CACHE, "w") as f:
        json.dump(id2dir, f)
    print(f"  {len(id2dir)} entries, cached")

# ---------- download helpers ----------
def download_one(url, out_path):
    """Download a single file. Returns 'ok', 'skip', or 'fail'."""
    if os.path.exists(out_path):
        return "skip"
    try:
        data = fetch(url)
        with open(out_path, "wb") as f:
            f.write(data)
        return "ok"
    except Exception as e:
        print(f"  [FAIL] {os.path.basename(out_path)}: {e}")
        return "fail"

def download_unown():
    """Download all Unown forms with shared palettes."""
    nat_id = 201
    dirname = "unown"
    stats = {"ok": 0, "skip": 0, "fail": 0}

    # shared palettes
    for pal in ("normal.pal", "shiny.pal"):
        url = f"{PRET_BASE}/{dirname}/{pal}"
        out = os.path.join(RES_DIR, f"{nat_id}_{pal}")
        res = download_one(url, out)
        stats[res] += 1
        time.sleep(0.02)

    for pret_form, suffix in UNOWN_FORM_MAP:
        # sprite — unown has no default form, only per-form files
        src = os.path.join(PRET_BASE, dirname, pret_form, "front.png")
        dst = os.path.join(RES_DIR, f"{nat_id}-{suffix}.png")
        res = copy_one(src, dst)
        stats[res] += 1

    print(f"  unown: ok={stats['ok']} skip={stats['skip']} fail={stats['fail']}")
    return stats

def download_castform():
    """Download all Castform forms with per-form palettes."""
    nat_id = 351
    dirname = "castform"
    stats = {"ok": 0, "skip": 0, "fail": 0}

    for pret_form, suffix in CASTFORM_FORMS:
        subdir = f"{dirname}/{pret_form}"
        out_name = f"{nat_id}" if suffix == "" else f"{nat_id}-{suffix}"
        targets = [
            (f"{PRET_BASE}/{subdir}/front.png",  f"{out_name}.png"),
            (f"{PRET_BASE}/{subdir}/normal.pal", f"{out_name}_normal.pal"),
            (f"{PRET_BASE}/{subdir}/shiny.pal",  f"{out_name}_shiny.pal"),
        ]
        for url, fname in targets:
            out = os.path.join(RES_DIR, fname)
            res = download_one(url, out)
            stats[res] += 1
            time.sleep(0.02)

    print(f"  castform: ok={stats['ok']} skip={stats['skip']} fail={stats['fail']}")
    return stats

def download_deoxys():
    """Download Deoxys raw sprites. Cropping to be done in generate_appearance."""
    nat_id = 386
    dirname = "deoxys"
    stats = {"ok": 0, "skip": 0, "fail": 0}

    # front.png (64x128: normal top, attack bottom) -> 386.png
    # front_def.png (64x128: normal top, defense bottom) -> 386_def.png
    # shared palettes
    targets = [
        (f"{PRET_BASE}/{dirname}/front.png",     f"{nat_id}.png"),
        (f"{PRET_BASE}/{dirname}/front_def.png", f"{nat_id}_def.png"),
        (f"{PRET_BASE}/{dirname}/normal.pal",    f"{nat_id}_normal.pal"),
        (f"{PRET_BASE}/{dirname}/shiny.pal",     f"{nat_id}_shiny.pal"),
    ]
    for url, fname in targets:
        out = os.path.join(RES_DIR, fname)
        res = download_one(url, out)
        stats[res] += 1
        time.sleep(0.02)

    print(f"  deoxys: ok={stats['ok']} skip={stats['skip']} fail={stats['fail']}")
    return stats

# ---------- main download loop ----------
ok, fail, skip = 0, 0, 0

for nat_id in range(1, 387):
    dirname = id2dir.get(nat_id)
    if not dirname:
        continue

    # multi-form special cases
    if dirname == "unown":
        s = download_unown()
        ok += s["ok"]; skip += s["skip"]; fail += s["fail"]
        continue
    if dirname == "castform":
        s = download_castform()
        ok += s["ok"]; skip += s["skip"]; fail += s["fail"]
        continue
    if dirname == "deoxys":
        s = download_deoxys()
        ok += s["ok"]; skip += s["skip"]; fail += s["fail"]
        continue

    # standard single-form
    targets = [
        (f"{PRET_BASE}/{dirname}/front.png",    os.path.join(RES_DIR, f"{nat_id}.png")),
        (f"{PRET_BASE}/{dirname}/normal.pal",   os.path.join(RES_DIR, f"{nat_id}_normal.pal")),
        (f"{PRET_BASE}/{dirname}/shiny.pal",    os.path.join(RES_DIR, f"{nat_id}_shiny.pal")),
    ]
    for url, out_path in targets:
        res = download_one(url, out_path)
        if res == "ok":
            ok += 1
        elif res == "skip":
            skip += 1
        else:
            fail += 1
        time.sleep(0.02)

    if nat_id % 50 == 0:
        print(f"  ... {nat_id}/386  ok={ok} fail={fail} skip={skip}")

print(f"\nDone: ok={ok} fail={fail} skip={skip}")
print(f"Resources: {len(os.listdir(RES_DIR))} files in {RES_DIR}")

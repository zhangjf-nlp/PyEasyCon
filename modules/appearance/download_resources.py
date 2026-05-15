"""
Download raw resources into modules/appearance/resources/:
  {id}.png       - pret/pokefirered front.png (4-bit colormap, raw)
  {id}_normal.pal
  {id}_shiny.pal
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

RES_DIR   = os.path.join(os.path.dirname(__file__), "resources")
os.makedirs(RES_DIR, exist_ok=True)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=15) as r:
        return r.read()

MANUAL_OVERRIDES = {
    "farfetch-d": "farfetchd",
    "mr-mime":    "mr_mime",
    "ho-oh":      "ho_oh",
    "mime-jr":    "mime_jr",
    "porygon-z":  "porygon_z",
    "castform":   "castform/normal",
}

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
        if api_name == "unown":
            continue
        id2dir[nat_id] = api_to_pret_dir(api_name)
    with open(CACHE, "w") as f:
        json.dump(id2dir, f)
    print(f"  {len(id2dir)} entries, cached")

# ---------- download ----------
ok, fail, skip = 0, 0, 0
for nat_id in range(1, 387):
    dirname = id2dir.get(nat_id)
    if not dirname:
        continue
    targets = [
        (f"{PRET_BASE}/{dirname}/front.png",    os.path.join(RES_DIR, f"{nat_id}.png")),
        (f"{PRET_BASE}/{dirname}/normal.pal",   os.path.join(RES_DIR, f"{nat_id}_normal.pal")),
        (f"{PRET_BASE}/{dirname}/shiny.pal",    os.path.join(RES_DIR, f"{nat_id}_shiny.pal")),
    ]
    for url, out_path in targets:
        if os.path.exists(out_path):
            skip += 1
            continue
        try:
            data = fetch(url)
            with open(out_path, "wb") as f:
                f.write(data)
            ok += 1
        except urllib.error.HTTPError as e:
            fail += 1
            print(f"  [FAIL] #{nat_id:03d} {os.path.basename(out_path)}: HTTP {e.code}")
        except Exception as e:
            fail += 1
            print(f"  [FAIL] #{nat_id:03d} {os.path.basename(out_path)}: {e}")
        time.sleep(0.02)
    if nat_id % 50 == 0:
        print(f"  ... {nat_id}/386  ok={ok} fail={fail} skip={skip}")

print(f"\nDone: ok={ok} fail={fail} skip={skip}")
print(f"Resources: {len(os.listdir(RES_DIR))} files in {RES_DIR}")


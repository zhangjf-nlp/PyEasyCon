"""
下载 FRLG 全部 386 只宝可梦的普通/闪光形象图片。
来源: PokeAPI sprites (GitHub)
普通: https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-iii/firered-leafgreen/{id}.png
闪光: https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-iii/firered-leafgreen/shiny/{id}.png
保存到: modules/appearance/normal/{id}.png 和 modules/appearance/shiny/{id}.png
"""
import os
import time
import urllib.request

OUT_DIR = os.path.join(os.path.dirname(__file__), 'modules', 'appearance')
NORMAL_DIR = os.path.join(OUT_DIR, 'normal')
SHINY_DIR = os.path.join(OUT_DIR, 'shiny')

BASE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-iii/firered-leafgreen"

os.makedirs(NORMAL_DIR, exist_ok=True)
os.makedirs(SHINY_DIR, exist_ok=True)

HEADERS = {"User-Agent": "EasyCon-sprites-downloader/1.0"}

total, ok, fail = 0, 0, 0

for dex_id in range(1, 387):
    for subdir, label in [(NORMAL_DIR, "normal"), (SHINY_DIR, "shiny")]:
        total += 1
        url = f"{BASE_URL}/{label}/{dex_id}.png" if label == "shiny" else f"{BASE_URL}/{dex_id}.png"
        out_path = os.path.join(subdir, f"{dex_id}.png")
        if os.path.exists(out_path):
            ok += 1
            continue
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with open(out_path, 'wb') as f:
                f.write(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[FAIL] #{dex_id:03d} {label}: {e}")
    if dex_id % 20 == 0:
        print(f"  ... {dex_id}/386  ok={ok} fail={fail}")

print(f"\nDone: {ok}/{total} downloaded, {fail} failed")

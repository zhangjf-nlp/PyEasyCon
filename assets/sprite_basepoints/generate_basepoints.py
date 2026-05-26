import json
import os
import re

ref_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ref.txt")
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "basepoints.json")

basepoints = {}
with open(ref_path, "r", encoding="utf-8") as f:
    for line in f:
        m = re.search(r'\{\{lop/ev\|(\d+)\|(.+?)\|(\d+)\|(\d)\|(\d)\|(\d)\|(\d)\|(\d)\|(\d)\}\}', line)
        if m:
            sid = int(m.group(1))
            basepoints[sid] = {
                "zh_name": m.group(2),
                "hp": int(m.group(4)),
                "attack": int(m.group(5)),
                "defense": int(m.group(6)),
                "sp_atk": int(m.group(7)),
                "sp_def": int(m.group(8)),
                "speed": int(m.group(9)),
            }

os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(basepoints, f, ensure_ascii=False, indent=2)

print(f"Generated {out_path} with {len(basepoints)} species.")

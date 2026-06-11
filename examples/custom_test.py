# -*- coding: utf-8 -*-
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from gui import run_script
from script_utils.navigation import navigate_safari_zone, restart, navigate, reverse_route_map

TARGET_ROUTE_MAP = {
    "center_grass": [
        ("run", [("LEFT", 2), ("UP", 3)]),
    ],
    "center_rod": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
    ],
    "center_surfing": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 1)]),
    ],
    "east_grass": [
        ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
        ("wait", [("RIGHT", 1)]),
        ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 12)]),
    ],
    "east_rod": [
        ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
        ("wait", [("RIGHT", 1)]),
        ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 19), ("UP", 4),
                 ("LEFT", 6), ("DOWN", 2), ("LEFT", 6), ("UP", 5), ("RIGHT", 1)]),
    ],
    "east_surfing": [
        ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
        ("wait", [("RIGHT", 1)]),
        ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 19), ("UP", 4),
                 ("LEFT", 6), ("DOWN", 2), ("LEFT", 6), ("UP", 5), ("RIGHT", 1)]),
        ("surf", [("RIGHT", 1)]),
    ],
    "north_grass": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 6), ("LEFT", 6), ("UP", 1)]),
        ("run", [("UP", 8)]),
        ("wait", [("UP", 1)]),
        ("run", [("UP", 2)]),
    ],
    "north_rod": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 6), ("LEFT", 6), ("UP", 1)]),
        ("run", [("UP", 8)]),
        ("wait", [("UP", 1)]),
        ("run", [("UP", 11), ("LEFT", 6), ("DOWN", 5), ("LEFT", 4)]),
    ],
    "north_surfing": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 6), ("LEFT", 6), ("UP", 1)]),
        ("run", [("UP", 8)]),
        ("wait", [("UP", 1)]),
        ("run", [("UP", 11), ("LEFT", 6), ("DOWN", 5), ("LEFT", 4)]),
        ("surf", [("LEFT", 1)]),
    ],
    "west_grass": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 1), ("LEFT", 15)]),
        ("run", [("LEFT", 10)]),
        ("wait", [("LEFT", 1)]),
        ("run", [("LEFT", 10), ("UP", 5), ("LEFT", 5), ("DOWN", 2),
                 ("LEFT", 10), ("DOWN", 3)]),
    ],
    "west_rod": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 1), ("LEFT", 15)]),
        ("run", [("LEFT", 10)]),
        ("wait", [("LEFT", 1)]),
        ("run", [("LEFT", 10), ("UP", 5), ("LEFT", 5), ("DOWN", 2),
                 ("LEFT", 10), ("DOWN", 3), ("LEFT", 5), ("UP", 7)]),
    ],
    "west_surfing": [
        ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ("surf", [("UP", 1), ("LEFT", 15)]),
        ("run", [("LEFT", 10)]),
        ("wait", [("LEFT", 1)]),
        ("run", [("LEFT", 10), ("UP", 5), ("LEFT", 5), ("DOWN", 2),
                 ("LEFT", 10), ("DOWN", 3), ("LEFT", 5), ("UP", 7)]),
        ("surf", [("UP", 1)]),
    ],
}


def get_forward_final_direction(route_map):
    """获取正向路线最后停留的方向"""
    for way, route in reversed(route_map):
        if way == "wait":
            continue
        if route:
            return route[-1][0]
    return "UP"


def main(ctx: ScriptContext) -> None:
    for zone in ["center", "north", "east", "west"]:
        for category in ["grass", "rod", "surfing"]:
            for _ in range(40):
                ctx.press("A")
                time.sleep(0.5)
            ctx.log(f"start to test {zone}_{category}")

            # 正向 + 逆向连续录屏
            ctx.screen_record_start()
            start = time.time()

            # 正向导航
            final_dir = navigate_safari_zone(ctx, f"{zone}_{category}")

            # 逆向导航
            route_map = TARGET_ROUTE_MAP[f"{zone}_{category}"]
            rev_map = reverse_route_map(route_map)
            final_dir = navigate(ctx, route_map=rev_map, current_direction=final_dir)

            end = time.time()
            seconds = int(end - start)
            save_path = f"screen_records/{zone}_{category}_{seconds}s.mp4"
            ctx.screen_record_save(save_path)
            ctx.log(f"save to {save_path}")
            time.sleep(3.0)

            restart(ctx)


if __name__ == "__main__":
    run_script(main)

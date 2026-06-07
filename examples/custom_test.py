# -*- coding: utf-8 -*-
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from gui import run_script
from script_utils.navigation import navigate_safari_zone, restart


def main(ctx: ScriptContext) -> None:
    for zone in ["center", "north", "east", "west"]:
        for category in ["grass", "rod", "surfing"]:
            for _ in range(40):
                ctx.press("A")
                time.sleep(0.5)
            ctx.log(f"start to test {zone}_{category}")
            ctx.screen_record_start()
            start = time.time()
            navigate_safari_zone(ctx, f"{zone}_{category}")
            end = time.time()
            ctx.screen_record_end()
            seconds = int(end - start)
            save_path = f"screen_records/{zone}_{category}_{seconds}s.mp4"
            ctx.screen_record_save(save_path)
            ctx.log(f"save to {save_path}")
            time.sleep(3.0)
            restart(ctx)


if __name__ == "__main__":
    run_script(main)

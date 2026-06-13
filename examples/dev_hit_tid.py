# -*- coding: utf-8 -*-
import sys
import os
import time

from numpy.char import isdigit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycon.context import ScriptContext
from easycon.controller import sleep
from gui import run_script
from script_utils.navigation import restart, enter_name

config_gender = "girl" # "boy" / "girl"
config_name = "JETT"
config_partner_name = "NULL"

def hit_seed(ctx: ScriptContext, seed_ms: int = 35000, f1_ms: int = 50000, f2_ms: int = 30000, f3_ms: int = 60000):
    tids = []
    for i in range(100):
        seed_time = time.time() + seed_ms / 1000.0
        f1_time = seed_time + f1_ms / 1000.0
        f2_time = f1_time + f2_ms / 1000.0
        f3_time = f2_time + f3_ms / 1000.0
        ctx.press("A") # 进入游戏

        sleep(0.0, end=seed_time)
        ctx.press("A", 4000) # 在封面界面按下按键
        sleep(1.0)

        ctx.press("DOWN")
        sleep(1.0)
        ctx.press("A")
        sleep(1.0)
        for _ in range(10):
            ctx.press("A")
            sleep(1.0)
        sleep(1.0)
        for _ in range(20):
            ctx.press("B")
            sleep(1.0)
        sleep(1.0)
        if config_gender == "girl":
            ctx.press("DOWN")
            sleep(1.0)
            ctx.press("A")
            sleep(1.0)
        else:
            ctx.press("A")
            sleep(1.0)
        
        sleep(0.0, end=f1_time)
        ctx.press("A") # 进入取名前的界面按下按键
        sleep(3.0)

        enter_name(ctx, config_name)
        
        sleep(0.0, end=f2_time)
        ctx.press("A") # 取名按下OK
        sleep(3.0)

        ctx.press("A")
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)

        enter_name(ctx, config_partner_name)
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)
        ctx.press("A")
        sleep(3.0)

        sleep(0.0, end=f3_time)
        ctx.press("A") # 主角缩小前最后一句话按下按键
        sleep(8.0)

        ctx.press("X")
        sleep(2.0)
        ctx.press("DOWN")
        sleep(1.0)
        ctx.press("A")
        sleep(3.0)

        result = ctx.ocr("TRAINER_CARD")
        tid: str = result['tid']
        if tid.isdigit():
            tid = int(tid)
            tids.append(tid)
            tids = sorted(tids)
            ctx.log(f"{tids=}")
        
        restart(ctx)
        sleep(3.0)



def main(ctx: ScriptContext) -> None:
    hit_seed(ctx)


if __name__ == "__main__":
    run_script(main)
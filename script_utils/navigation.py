from easycon.context import ScriptContext
from script_utils.hit import sleep


def restart(ctx: ScriptContext) -> None:
    ctx.log("重启游戏...")
    for _ in range(30):
        ctx.press("HOME")
        sleep(3.0)
        if ctx.search_label("NS主页满电量", 90):
            break
    ctx.press("X")
    sleep(1.0)
    for _ in range(10):
        ctx.press("A")
        sleep(3.0)
        if ctx.search_label("NS主页选择玩家", 90):
            break

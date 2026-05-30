from easycon.context import ScriptContext
from script_utils.hit import sleep


def restart(ctx: ScriptContext) -> None:
    ctx.log("重启游戏...")
    if ctx.search_label("NS主页满电量", 90):
        pass
    else:
        ctx.press("HOME")
        sleep(2.0)
    if ctx.search_label("NS主页关闭确认", 90):
        ctx.press("A")
    else:
        ctx.press("Y")
        sleep(2.0)
        ctx.press("A")
    for _ in range(5):
        sleep(1.0)
        if ctx.search_label("NS主页选择玩家", 40):
            break
    else:
        raise ValueError("未检测到NS选择玩家界面")
    sleep(1.0)

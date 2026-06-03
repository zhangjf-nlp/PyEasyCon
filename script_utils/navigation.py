from easycon.context import ScriptContext
from script_utils.hit import sleep


def run_away(ctx: ScriptContext) -> None:
    for _ in range(15):
        ctx.press("B")
        sleep(0.3)
        ctx.press("DOWN")
        sleep(0.3)
        ctx.press("RIGHT")
        sleep(0.3)
        if ctx.search_label("FRLG逃跑", 90):
            ctx.press("A")
            sleep(1.0)
            break
    for _ in range(30):
        sleep(0.5)
        if in_wild(ctx):
            return
        ctx.press("B")
        sleep(0.3)


def in_wild(ctx: ScriptContext) -> bool:
    return ctx.search_label("FRLG草丛", 90) or ctx.search_label("FRLG对话", 90) \
        or ctx.search_label("FRLG水面", 90) or ctx.search_label("FRLG洞穴", 90)


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

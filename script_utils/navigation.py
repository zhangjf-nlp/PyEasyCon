from typing import List, Tuple
from easycon.context import ScriptContext, sleep

unit_move_ms = 16 / 60 * 1000
unit_swing_ms = 8 / 60 * 1000


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
        or ctx.search_label("FRLG水面", 90) or ctx.search_label("FRLG洞穴", 90) \
        or ctx.search_label("FRLG宝可梦塔", 90)


def restart(ctx: ScriptContext) -> None:
    ctx.log("重启游戏...")
    search_label_zysb = lambda : any(ctx.search_label(f"NS{_}色系主题-主页手柄", 80) for _ in "深浅")
    search_label_qhyh = lambda : any(ctx.search_label(f"NS{_}色系主题-切换用户", 80) for _ in "深浅")
    search_label_ysyw = lambda : any(ctx.search_label(f"NS{_}色系主题-由谁游玩", 80) for _ in "深浅")
    
    for _ in range(5):
        if search_label_zysb() and not search_label_ysyw():
            break
        else:
            ctx.press("HOME")
            sleep(3.0)
    else:
        ctx.log(f"[重启失败警告] 未能识别到NS主页画面")
    
    for _ in range(5):
        if search_label_qhyh():
            break
        else:
            ctx.press("Y")
            sleep(3.0)
    else:
        ctx.log(f"[重启失败警告] 未能识别到用户切换画面")
    sleep(3.0)
    ctx.press("A")
    
    for _ in range(5):
        if search_label_zysb() and search_label_ysyw():
            break
        else:
            sleep(1.0)
    else:
        ctx.log(f"[重启失败警告] 未能识别到用户选择画面")
    sleep(1.0)


def navigate(ctx: ScriptContext, route_map: List[Tuple[str, List[Tuple[str, int]]]], current_direction: str = None) -> None:
    for way, route in route_map:
        if way == "wait":
            sleep(1.0)
            continue
        if way not in ["walk", "run", "surf"]:
            raise NotImplementedError(way)
        speed_ratio = {"walk": 1, "run": 2, "surf": 2}[way]
        # start
        if way == "walk":
            pass
        elif way == "run":
            ctx.hold("B")
            sleep(0.5)
        elif way == "surf":
            for _ in range(5):
                ctx.press("A")
                sleep(0.5)
            sleep(2.0)
        # head
        for direction, units in route:
            heading_time = (units - 0.5) * unit_move_ms / speed_ratio
            heading_time += unit_swing_ms if (direction != current_direction) else 0
            ctx.press(direction, heading_time)
            current_direction = direction
            sleep(0.35)
        # end
        if way == "walk":
            pass
        if way == "run":
            ctx.release("B")
            sleep(0.5)
        elif way == "surf":
            sleep(0.5)


def navigate_safari_zone(ctx: ScriptContext, target: str):
    ctx.press("UP")
    sleep(1.0)
    for _ in range(20):
        ctx.press("A")
        sleep(0.5)
    sleep(2.0)

    current_direction = "UP"
    target_route_map = {
        "center_grass": [
            ("run", [("LEFT", 2), ("UP", 3)]),
        ],
        "center_rod": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
        ],
        "center_surfing": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", []),
        ],
        "east_grass": [
            ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
            ("wait", []),
            ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 12)]),
        ],
        "east_rod": [
            ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
            ("wait", []),
            ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 19), ("UP", 4),
                     ("LEFT", 6), ("DOWN", 2), ("LEFT", 6), ("UP", 5), ("RIGHT", 1)]),
        ],
        "east_surfing": [
            ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
            ("wait", []),
            ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 19), ("UP", 4),
                     ("LEFT", 6), ("DOWN", 2), ("LEFT", 6), ("UP", 5), ("RIGHT", 1)]),
            ("surf", []),
        ],
        "north_grass": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", [("UP", 5), ("LEFT", 6), ("UP", 1)]),
            ("run", [("UP", 8)]),
            ("wait", []),
            ("run", [("UP", 2)]),
        ],
        "north_rod": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", [("UP", 5), ("LEFT", 6), ("UP", 1)]),
            ("run", [("UP", 8)]),
            ("wait", []),
            ("run", [("UP", 11), ("LEFT", 6), ("DOWN", 5), ("LEFT", 4)]),
        ],
        "north_surfing": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", [("UP", 5), ("LEFT", 6), ("UP", 1)]),
            ("run", [("UP", 8)]),
            ("wait", []),
            ("run", [("UP", 11), ("LEFT", 6), ("DOWN", 5), ("LEFT", 4)]),
            ("surf", []),
        ],
        "west_grass": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", [("LEFT", 15)]),
            ("run", [("LEFT", 10)]),
            ("wait", []),
            ("run", [("LEFT", 10), ("UP", 5), ("LEFT", 5), ("DOWN", 2),
                     ("LEFT", 10), ("DOWN", 3)]),
        ],
        "west_rod": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", [("LEFT", 15)]),
            ("run", [("LEFT", 10)]),
            ("wait", []),
            ("run", [("LEFT", 10), ("UP", 5), ("LEFT", 5), ("DOWN", 2),
                     ("LEFT", 10), ("DOWN", 3), ("LEFT", 5), ("UP", 7)]),
        ],
        "west_surfing": [
            ("run", [("UP", 9), ("RIGHT", 6), ("UP", 2)]),
            ("surf", [("LEFT", 15)]),
            ("run", [("LEFT", 10)]),
            ("wait", []),
            ("run", [("LEFT", 10), ("UP", 5), ("LEFT", 5), ("DOWN", 2),
                     ("LEFT", 10), ("DOWN", 3), ("LEFT", 5), ("UP", 7)]),
            ("surf", []),
        ]
    }
    
    navigate(
        ctx=ctx,
        route_map=target_route_map[target.lower()],
        current_direction=current_direction
    )

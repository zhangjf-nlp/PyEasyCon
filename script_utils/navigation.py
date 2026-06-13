import time
from dataclasses import dataclass
from typing import List, Tuple
from easycon.context import ScriptContext
from easycon.controller import sleep

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
    return any([
        ctx.search_label("FRLG草丛", 90),
        ctx.search_label("FRLG对话", 90),
        ctx.search_label("FRLG水面", 90),
        ctx.search_label("FRLG洞穴", 90),
        ctx.search_label("FRLG宝可梦塔", 85),
    ]) and not any([
        ctx.search_label(f"NS深色系主题-主页手柄", 80),
        ctx.search_label(f"NS浅色系主题-主页手柄", 80),
    ])


def restart(ctx: ScriptContext) -> None:
    ctx.log("重启游戏...")
    search_label_zysb = lambda : any(ctx.search_label(f"NS{_}色系主题-主页手柄", 70) for _ in "深浅")
    search_label_qhyh = lambda : any(ctx.search_label(f"NS{_}色系主题-切换用户", 70) for _ in "深浅")
    search_label_ysyw = lambda : any(ctx.search_label(f"NS{_}色系主题-由谁游玩", 70) for _ in "深浅")
    
    ctx.screen_record_start()
    warning = False
    
    for _ in range(3):
        ctx.press("HOME")
        for __ in range(50):
            if search_label_zysb() and not search_label_ysyw():
                break
            else:
                time.sleep(0.1)
        else:
            continue
        break
    else:
        ctx.log(f"[重启失败警告] 未能识别到NS主页画面")
        warning = True
    time.sleep(1.0)
    
    for _ in range(3):
        ctx.press("Y")
        for __ in range(50):
            if search_label_qhyh():
                break
            else:
                time.sleep(0.1)
        else:
            continue
        break
    else:
        ctx.log(f"[重启失败警告] 未能识别到用户切换画面")
        warning = True
    time.sleep(1.0)
    
    ctx.press("A")
    for _ in range(3):
        for __ in range(50):
            if search_label_zysb() and search_label_ysyw():
                break
            else:
                time.sleep(0.1)
        else:
            if search_label_zysb() and not search_label_ysyw():
                ctx.press("A")
            continue
        break
    else:
        ctx.log(f"[重启失败警告] 未能识别到用户切换画面")
        warning = True
    time.sleep(1.0)

    if warning:
        ctx.screen_record_save("restart_with_warning.mp4")
    else:
        ctx.recording_flag = False
        ctx.record_frames.clear()


def navigate(ctx: ScriptContext, route_map: List[Tuple[str, List[Tuple[str, int]]]], current_direction: str = None) -> str:
    for way, route in route_map:
        if way == "wait":
            assert len(route) == 1, route
            current_direction, delay_seconds = route[0]
            sleep(delay_seconds)
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
            first_dir, first_units = route[0]
            if first_dir != current_direction:
                ctx.press(first_dir)
                sleep(0.5)
            for _ in range(5):
                ctx.press("A")
                sleep(0.5)
            sleep(2.0)
            route = [(first_dir, first_units - 1)] + route[1:] if first_units > 1 else route[1:]
        # head
        for direction, units in route:
            heading_time = (units - 0.4) * unit_move_ms / speed_ratio
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

    return current_direction


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
    
    return navigate(
        ctx=ctx,
        route_map=target_route_map[target.lower()],
        current_direction=current_direction
    )


def reverse_route_map(map: List[Tuple[str, List[Tuple[str, int]]]]):
    """
    按照以下规则完善现有的reverse计算
    [
        ("run", [("UP", 1), ("RIGHT", 16), ("UP", 13), ("RIGHT", 2)]),
        ("wait", [("RIGHT", 1)]),
        ("run", [("RIGHT", 9), ("DOWN", 1), ("RIGHT", 19), ("UP", 4),
                    ("LEFT", 6), ("DOWN", 2), ("LEFT", 6), ("UP", 5), ("RIGHT", 1)]),
        ("surf", [("RIGHT", 1)]),
    ]
    -- reverse -->
    [
        ("surf", [("LEFT", 1)]),
        ("run", [("LEFT", 1), ..., ("LFET", 9), ("LEFT", 1)]), # 前面正常逆转; 正向以("wait", [("RIGHT", 1)])开始 -> 末尾添加一个wait逆向unit: ("LEFT", 1)
        ("wait", [("LEFT", 1)]), # 正向从("RIGHT", 2)进入wait -> wait方向变为LEFT & delay不变 & 下一行("RIGHT", 2)开头要减去一个unit
        ("run", [("LEFT", 1), ("DOWN", 13), ..., ("DOWN", 1)]), # 正向以wait结束 -> 开头减去一个unit: ("RIGHT", 2) -> ("LEFT", 2) -> ("LEFT", 1)
    ]

    [
        ("walk", [("RIGHT", 6), ("DOWN", 1), ("RIGHT", 6), ("UP", 1)]),
        ("wait", [("UP", 2)]),
        ("walk", [("UP", 9), ("RIGHT", 8)]),
        ("wait", [("LEFT", 1)]),
        ("walk", [("UP", 4), ("LEFT", 14), ("DOWN", 4), ("LEFT", 1)]),
        ("wait", [("RIGHT", 1)]),
    ]
    -- reverse -->
    [
        ("walk", [("LEFT", 1)]), # 正向以("wait", [("RIGHT", 1)])开始 -> 末尾添加一个wait逆向unit: ("LEFT", 1)
        ("wait", [("RIGHT", 1)]), # 正向从("LEFT", 1)进入wait -> wait方向变为RIGHT & delay不变 & 下一行("LEFT", 1)开头要减去一个unit
        ("walk", [("UP", 4), ("RIGHT", 14), ("DOWN", 4), ("RIGHT", 1)]), # 正向以wait结束 -> 开头减去一个unit: ("LEFT", 1) -> ("RIGHT", 1) -> ("RIGHT", 0) -> 消失
        # [承上]正向以("wait", [("UP", 2)])开始 -> 末尾添加一个wait逆向unit: ("RIGHT", 1)
        ("wait", [("LEFT", 1)]), # 正向从("RIGHT", 8)进入wait -> wait方向变为LEFT & delay不变 & 下一行("RIGHT", 8)开头要减去一个unit
        ("walk", [("LEFT", 7), ("DOWN", 9), ("DOWN", 1)]), # 正向以wait结束 -> 开头减去一个unit: ("RIGHT", 8) -> ("LEFT", 8) -> ("LEFT", 7)
        # [承上]正向以("wait", [("UP", 2)])开始 -> 末尾添加一个wait逆向unit: ("DOWN", 1)
        ("wait", [("DOWN", 2)]), # 正向从("UP", 1)进入wait -> wait方向变为DOWN & delay不变 & 下一行("UP", 1)开头要减去一个unit
        ("walk", [("LEFT", 6), ("UP", 1), ("LEFT", 6)]) # 正向以wait结束 -> 开头减去一个unit: ("UP", 1) -> ("DOWN", 1) -> ("DOWN", 0) -> 消失
    ]
    """
    reverse_direction = {
        "DOWN": "UP", "UP": "DOWN",
        "RIGHT": "LEFT", "LEFT": "RIGHT"
    }

    n = len(map)
    result: List[Tuple[str, List[Tuple[str, int]]]] = []

    # 正向以wait结尾 -> 逆向开头需插入一个walk/run segment（退回上一个地图）
    if n > 0 and map[-1][0] == "wait":
        wait_dir = map[-1][1][0][0]
        extra_dir = reverse_direction[wait_dir]
        extra_way = map[-2][0] if n >= 2 else "walk"
        result.append((extra_way, [(extra_dir, 1)]))
    
    for i in range(n - 1, -1, -1):
        way, route = map[i]

        if way == "wait":
            # wait方向 = 正向中前一个segment最后一步方向的逆向
            _, prev_route = map[i - 1]
            prev_last_dir = prev_route[-1][0]
            wait_dir = reverse_direction[prev_last_dir]
            wait_units = route[0][1]
            result.append(("wait", [(wait_dir, wait_units)]))
            continue

        # walk/run/surf：基本逆转（路线倒序、方向取反）
        rev_route = [(reverse_direction[d], u) for d, u in reversed(route)]

        if way in ("walk", "run"):
            # 进入wait -> 逆向中开头减去一个unit
            if i + 1 < n and map[i + 1][0] == "wait":
                first_dir, first_units = rev_route[0]
                if first_units > 1:
                    rev_route[0] = (first_dir, first_units - 1)
                else:
                    rev_route = rev_route[1:]

            # 从wait进入 -> 逆向中末尾添加一个逆向unit
            if i - 1 >= 0 and map[i - 1][0] == "wait":
                wait_dir = map[i - 1][1][0][0]
                rev_route.append((reverse_direction[wait_dir], 1))

        result.append((way, rev_route))
    
    if n > 0 and result[0][0] == "surf":
        result[0][1][0] = (result[0][1][0][0], result[0][1][0][1] + 1)
    
    return result


def enter_name(ctx: ScriptContext, name: str):
    keyboards = [[
        "ABCDEF .",
        "GHIJKL ,",
        "MNOPQRS ",
        "TUVWXYZ ",
    ], [
        "abcdef .",
        "ghijkl ,",
        "mnopqrs ",
        "tuvwxyz ",
    ], [
        "01234 ",
        "56789 ",
        "!?♀♂/-",
        "…“”‘’ ",
    ]]
    
    if len(name) > 7:
        raise ValueError(f"[invalid name] Name too long {list(name)}")
    
    @dataclass
    class Location:
        k: int = 0
        r: int = 0
        c: int = 0

    def locate_char(char: str) -> Location:
        assert len(char) == 1
        for k, keyboard in enumerate(keyboards):
            for r, row in enumerate(keyboard):
                if char in row:
                    return Location(k=k, r=r, c=row.index(char))
        raise ValueError(f"[invalid name] Name char not found {char}")
    
    def enter_char(char: str, src: Location) -> Location:
        assert len(char) == 1
        dst = locate_char(char)
        if dst.k != src.k:
            for _ in range(src.r):
                ctx.press("UP")
                sleep(1.0)
            for _ in range(src.c):
                ctx.press("LEFT")
                sleep(1.0)
            for _ in range((dst.k - src.k) % 3):
                ctx.press("Y")
                sleep(1.5)
            for _ in range(dst.c):
                ctx.press("RIGHT")
                sleep(1.0)
            for _ in range(dst.r):
                ctx.press("DOWN")
                sleep(1.0)
        else:
            steps = abs(dst.r - src.r)
            button = "DOWN" if dst.r > src.r else "UP"
            for _ in range(steps):
                ctx.press(button)
                sleep(1.0)
            steps = abs(dst.c - src.c)
            button = "RIGHT" if dst.c > src.c else "LEFT"
            for _ in range(steps):
                ctx.press(button)
                sleep(1.0)
        
        ctx.press("A")
        return dst
    
    src = Location(k=0, r=0, c=0)
    for char in name:
        src = enter_char(char, src)
        sleep(2.0)
    
    ctx.press("X")
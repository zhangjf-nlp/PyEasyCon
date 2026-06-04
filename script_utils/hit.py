import time
from typing import Optional

from easycon.context import ScriptContext
from rng.config import RNGConfig


def sleep(seconds: float, end: Optional[float] = None) -> None:
    start = time.time()
    if end is None:
        mid = start + seconds - 0.1
        end = start + seconds
    else:
        mid = end - 0.1
    while True:
        if time.time() >= mid:
            if time.time() >= end:
                return
        else:
            time.sleep(0.05)


def hit_init_seed(ctx: ScriptContext, cfg: RNGConfig) -> None:
    sb, eb = cfg.game_settings.seed_button, cfg.game_settings.extra_button
    EB = eb[-1].upper() if eb in ["blackout_r", "blackout_l"] else None
    SB = {"start": "PLUS", "a": "A", "l": "L"}[sb]
    time_start = time.time()
    ctx.press("A")
    time_end = time_start + cfg.schedule.seed_ms / 1000
    if EB:
        while not ctx.search_label("FRLGCopyright", 90):
            sleep(0.1)
        ctx.press(EB, 3000)
    sleep(0.0, end=time_end)
    ctx.press(SB, 4000)
    sleep(1.0)
    ctx.press("A")
    sleep(1.0)
    ctx.press("B")
    sleep(3.0)


def hit_tv_frame(ctx: ScriptContext, cfg: RNGConfig) -> None:
    ctx.press("Y")
    sleep(cfg.schedule.advances_ms_tv / 1000.0)
    ctx.press("B")
    sleep(1.0)


def hit_sweet_scent(ctx: ScriptContext, cfg: RNGConfig) -> None:
    start = time.time()
    end = start + cfg.schedule.advances_ms_normal / 1000.0
    ctx.press("X")
    sleep(1.0)
    ctx.press("DOWN")
    sleep(0.5)
    ctx.press("A")
    sleep(2.0)
    ctx.press("A")
    sleep(1.5)
    ctx.press("DOWN")
    sleep(0.0, end)
    ctx.press("A")


def hit_super_rod(ctx: ScriptContext, cfg: RNGConfig) -> None:
    start = time.time()
    end = start + cfg.schedule.advances_ms_normal / 1000.0
    ctx.press("X")
    sleep(1.0)
    ctx.press("DOWN")
    sleep(0.5)
    ctx.press("DOWN")
    sleep(0.5)
    ctx.press("A")
    sleep(1.0)
    ctx.press("RIGHT")
    sleep(1.0)
    reversed = False
    for _ in range(30):
        if ctx.search_label(f"FRLG关键词选中CANCEL", 90):
            reversed = True
        score = ctx.search_label(f"FRLG关键词{cfg.rng_category}选中", -1)
        import cv2
        cv2.imwrite(f"tmp-{_:0>2d}-{score}.png", ctx.get_frame().copy())
        if score >= 80:
            break
        else:
            ctx.press("DOWN" if not reversed else "UP", duration_ms=100)
            sleep(0.5)
    else:
        ctx.log(f'未找到{cfg.rng_category}')
        return
    ctx.press("A")
    sleep(0.5)
    ctx.press("A")
    sleep(0.0, end)
    ctx.press("A")


def hit_game_corner(ctx: ScriptContext, cfg: RNGConfig) -> None:
    start = time.time()
    end = start + cfg.schedule.advances_ms_normal / 1000.0
    ctx.press("A")
    sleep(1.5)
    ctx.press("A")
    sleep(1.5)
    if cfg.game_version in ["fr_nx", "fr_nx2"]:
        pokemon_list = ["Abra", "Clefairy", "Dratini", "Scyther", "Porygon"]
    elif cfg.game_version in ["lg_nx", "lg_nx2"]:
        pokemon_list = ["Abra", "Clefairy", "Pinsir", "Dratini", "Porygon"]
    else:
        raise NotImplementedError(f"暂未支持的游戏版本：{cfg.game_version}")
    for pokemon in pokemon_list:
        if pokemon == cfg.pokemon_species:
            break
        ctx.press('DOWN')
        sleep(0.8)
    else:
        raise ValueError(f"该版本游戏厅无预期宝可梦：{cfg.game_version}-{cfg.pokemon_species}")
    ctx.press('A')
    sleep(0.0, end)
    ctx.press('A')
    sleep(3.0)
    ctx.press("B")


def hit_A(ctx: ScriptContext, cfg: RNGConfig) -> None:
    start = time.time()
    end = start + cfg.schedule.advances_ms_normal / 1000.0
    extra_as = {
        "Lapras": 3,
        "Eevee": 0,
        "Snorlax": 1,
    }[cfg.pokemon_species]
    for _ in range(extra_as):
        ctx.press("A")
        sleep(3.0)
    sleep(0.0, end)
    ctx.press("A")
    sleep(3.0)
    ctx.press("B")


def hit(ctx: ScriptContext, cfg: RNGConfig) -> bool:
    ctx.log("--- RNG 流程启动 ---")
    hit_init_seed(ctx, cfg)
    if cfg.schedule.advances_ms_tv > 0:
        hit_tv_frame(ctx, cfg)
    if cfg.rng_category in ["Grass", "Surfing"]:
        hit_sweet_scent(ctx, cfg)
    elif cfg.rng_category == "SuperRod":
        hit_super_rod(ctx, cfg)
    elif cfg.rng_category == "Game Corner":
        hit_game_corner(ctx, cfg)
    elif cfg.rng_category in ["Gift", "Stationary"]:
        hit_A(ctx, cfg)
    else:
        raise NotImplementedError(cfg.rng_category)
    ctx.log("--- RNG 流程结束 ---")
    return True
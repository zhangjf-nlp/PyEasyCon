import time


def sleep(seconds, end=None):
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


def hit_init_seed(ctx, cfg):
    sb, eb = cfg.game_settings.seed_button, cfg.game_settings.extra_button
    ctx.press("A")
    sleep(0.1)
    if eb in ["blackout_r", "blackout_l"]:
        ctx.log(f"hold {eb[-1].upper()}")
        ctx.hold(eb[-1].upper())
    sleep(cfg.seed_ms / 1000.0)
    if eb in ["blackout_r", "blackout_l"]:
        ctx.log(f"release {eb[-1].upper()}")
        ctx.release(eb[-1].upper())
    if sb == "start":
        ctx.hold("PLUS")
        sleep(4.0)
        ctx.release("PLUS")
    else:
        assert sb in ["a", "l"], sb
        ctx.hold(sb.upper())
        sleep(4.0)
        ctx.release(sb.upper())
    sleep(1.0)
    ctx.press("A")
    sleep(1.0)
    ctx.press("B")
    sleep(3.0)


def hit_tv_frame(ctx, cfg):
    ctx.press("Y")
    sleep(cfg.advances_ms_tv / 1000.0)
    ctx.press("B")
    sleep(1.0)


def hit_sweet_scent(ctx, cfg):
    start = time.time()
    end = start + cfg.advances_ms_normal / 1000.0
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


def hit_super_rod(ctx, cfg):
    start = time.time()
    end = start + cfg.advances_ms_normal / 1000.0
    ctx.press("X")
    sleep(1.0)
    ctx.press("DOWN")
    sleep(0.5)
    ctx.press("DOWN")
    sleep(0.5)
    ctx.press("A")
    sleep(1.0)
    ctx.press("RIGHT")
    sleep(0.5)
    for _ in range(100):
        if ctx.search_label("3代关键词SuperRod选中", 99):
            break
        ctx.press("DOWN")
        sleep(0.5)
    else:
        ctx.log('未找到超级钓竿')
        return
    ctx.press("A")
    sleep(0.5)
    ctx.press("A")
    sleep(0.0, end)
    ctx.press("A")


def hit_game_corner(ctx, cfg):
    start = time.time()
    end = start + cfg.advances_ms_normal / 1000.0
    ctx.press("A")
    sleep(1.5)
    ctx.press("A")
    sleep(1.5)
    if cfg.game_version == "fr_nx":
        pokemon_list = ["Abra", "Clefairy", "Dratini", "Scyther", "Porygon"]
    elif cfg.game_version == "lg_nx":
        pokemon_list = ["Abra", "Clefairy", "Pinsir", "Dratini", "Porygon"]
    else:
        raise NotImplementedError(cfg.game_version)
    for pokemon in pokemon_list:
        if pokemon == cfg.pokemon_species:
            break
        ctx.press('DOWN')
        sleep(0.5)
    else:
        raise ValueError(f"版本游戏厅无预期宝可梦：{cfg.game_version}-{cfg.pokemon_species}")
    ctx.press('A')
    sleep(0.0, end)
    ctx.press('A')
    sleep(3.0)
    ctx.press("B")


def hit_gift(ctx, cfg):
    start = time.time()
    end = start + cfg.advances_ms_normal / 1000.0
    sleep(0.0, end)
    ctx.press("A")
    sleep(3.0)
    ctx.press("B")


def hit(ctx, cfg):
    ctx.log("--- RNG 流程启动 ---")
    hit_init_seed(ctx, cfg)
    if cfg.advances_ms_tv > 0:
        hit_tv_frame(ctx, cfg)
    if cfg.rng_category in ["Grass", "Surfing"]:
        hit_sweet_scent(ctx, cfg)
    elif cfg.rng_category == "SuperRod":
        hit_super_rod(ctx, cfg)
    elif cfg.rng_category == "Game Corner":
        hit_game_corner(ctx, cfg)
    elif cfg.rng_category == "Gift":
        hit_gift(ctx, cfg)
    else:
        raise NotImplementedError(cfg.rng_category)
    ctx.log("--- RNG 流程结束 ---")
    return True
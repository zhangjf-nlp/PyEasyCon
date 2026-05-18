from gui import run_script
from scripts.config import GameSettings, RNGConfig, TimingConfig, SessionState
from scripts.hit import hit
from scripts.capture import check_shiny, catch_with_ball, check_last_pokemon
from scripts.finetune import record_for_finetune
from scripts.navigation import restart


cfg = RNGConfig(
    game_version="fr_nx",
    trainer_id=58888,
    secret_id=12232,
    game_settings = GameSettings.from_string(
        "Mono | Help | Seed Button: A | Extra Button: None"
    ),
    pokemon_species="Mankey",
    rng_category="Grass",
    rng_location="Route 22",
    rng_method="All Wild Methods",
    seed_hex="920E",
    advances=1330536,
    seed_bias=-5047,
    advances_bias=-10143,
    timing=TimingConfig(operation_seconds=10.0),
)


def main(ctx):
    state = SessionState()

    ctx.log(f"GameSettings: {cfg.game_settings}")
    ctx.log(f"Seed={cfg.seed} Advances={cfg.advances}")
    ctx.log(f"SeedBias={cfg.seed_bias} AdvancesBias={cfg.advances_bias}")
    ctx.log(
        f"Seed takes {cfg.seed_ms}ms | TV takes {cfg.advances_ms_tv}ms "
        f"| Normal takes {cfg.advances_ms_normal}ms"
    )

    if cfg.seed_ms < 35000:
        ctx.log(f'[Warning] Too low seed time: {cfg.seed_ms}ms')
    if cfg.advances_ms_tv < 1000:
        ctx.log(f'[Warning] Too low TV time: {cfg.advances_ms_tv}ms')

    count = 0
    while ctx.is_running():
        count += 1
        ctx.log(f"========== 乱数尝试第 {count} 次 ==========")

        hit(ctx, cfg)

        if cfg.rng_category in ["Grass", "Surfing", "SuperRod"]:
            is_shiny, pokemon_en = check_shiny(ctx, cfg)
            if is_shiny:
                ctx.log("闪光出现!")
                break
            if pokemon_en:
                caught = catch_with_ball(ctx)
                if caught:
                    check_last_pokemon(ctx)
                    record_for_finetune(ctx, state, cfg, count, pokemon_en)
        elif cfg.rng_category == "Gift":
            check_last_pokemon(ctx)
            if ctx.search_label("3代闪光", 80):
                ctx.log("闪光出现!")
                break
            else:
                record_for_finetune(ctx, state, cfg, count, cfg.pokemon_species)
        else:
            raise NotImplementedError(cfg.rng_category)

        restart(ctx)

    ctx.press("CAPTURE", 3000)


if __name__ == "__main__":
    run_script(main)
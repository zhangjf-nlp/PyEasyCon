# Ten Lines Python API

A Python port of the [Ten Lines](https://lincoln-lm.github.io/ten-lines/) WebAssembly-based RNG manipulation toolkit for Generation 3 Pokémon games (Ruby/Sapphire/Emerald/FireRed/LeafGreen). All core logic is a 1:1 replica of the C++/WASM implementation, verified against live output from the production website.

**Performance:** The calibration engine is accelerated via pybind11 C++ bindings (2.6x faster for wild encounters, comparable for static). Falls back to pure Python automatically if the C++ module is not available.

## Background

RNG (Random Number Generator) manipulation exploits the deterministic nature of Pokémon's PRNG to predict or control encounter outcomes (IVs, nature, shininess, etc.). In Gen 3 FRLG, the initial seed is determined by a combination of button inputs and precise timing at boot. This toolkit provides three core functions:

- **Searcher** — Given desired IV/nature/shininess filters, find target seeds that produce matching Pokémon.
- **Initial Seed** — Given a target seed, find the button combinations and timing needed to hit that seed at boot.
- **Calibration** — Given a target initial seed and an advances range, generate all possible encounter outcomes to help calibrate your timing.

## Files

```
tenlines.py              # Core RNG, generator, searcher, calibration logic (1:1 C++ port)
tenlines_utils.py        # High-level API: searcher(), initial_seed(), calibration()
src/pybind/
  calibration_bind.cpp   # pybind11 C++ acceleration for calibration (standalone)
  setup.py               # Build script for pybind11 module
resources/
  fr_eng_nx.bin          # Pre-farmed FRLG seed data for Switch (NX) platform
  Personal/Gen3/personal_rsefrlg.bin   # Base stats, gender ratios, abilities
  i18n/en/species_en.txt               # English species names
  i18n/en/abilities_en.txt             # English ability names
  EncounterTables/Gen3/frlg/wild_encounters.json  # Wild encounter tables (FRLG)
test_tenlines.py         # Unit tests (29 tests, all passing)
verify_pybind.py         # Cross-validation: pybind11 C++ vs pure Python
cross_validate.py        # Cross-validation against C++ known values
benchmark/
  bench_full.py          # Full benchmark: pure Python vs pybind11 C++
  bench_calibration.py   # Calibration benchmark with numba comparison
  calibration_py.py      # Pure Python calibration implementations
```

## Quick Start

```python
from tenlines_utils import searcher, initial_seed, calibration, GameSettings, IVsRange, IVs

# --- Searcher: find seeds that produce a specific Pokémon ---
results = searcher(
    game="fr_nx",           # Switch FireRed
    console="NX",
    tid=58888, sid=12232,   # trainer ID, secret ID
    method="1",             # static method 1
    pokemon="1",            # Bulbasaur
    nature="Adamant",
    ivs_range=IVsRange(
        ivs_lower_bound=IVs(25, 25, 25, 0, 0, 0),
        ivs_upper_bound=IVs(31, 31, 31, 31, 31, 31),
    ),
)
for r in results:
    print(f"seed={r.target_seed} advances={r.advances} nature={r.nature} ivs={r.ivs}")

# --- Initial Seed: find button combos to hit a target seed ---
settings = GameSettings(sound="mono", button_mode="h", seed_button="a", extra_button="none")
seeds = initial_seed(
    game="fr_nx",
    target_seed="935EFF9E",  # 32-bit target seed
    count=10,
    settings=settings,
)
for s in seeds:
    print(f"seed={s.seed} advances={s.advances} seed_time={s.seed_time}ms settings={s.settings}")

# --- Calibration: generate encounter outcomes for timing calibration ---
cal = calibration(
    game="fr_nx",
    console="NX",
    tid=58888, sid=12232,
    method="1",
    seed="3A53",            # 16-bit initial seed (hex)
    advances=111679,        # expected advances
    settings=settings,
    seed_bias=20,           # search ±20 seeds around target
    advances_bias=500,      # search ±500 advances
    pokemon="1",            # species ID for correct gender ratio
)
for c in cal:
    print(f"seed={c.seed} advances={c.advances} pid={c.pid:08X} nature={c.nature} ivs={c.ivs}")
```

## API Reference

### `searcher(game, console, tid, sid, method, category, location, pokemon, shiny, nature, gender, hidden_type, ivs_range, seed_file, max_time_seconds) -> List[SearcherResult]`

Search for target seeds matching given filters. Iterates over all possible seeds (FRLG: pre-farmed list, RSE: painting seeds) and generates encounter outcomes.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `game` | str | `"fr_nx"` | Game version (e.g. `"fr"`, `"fr_nx"`, `"r_painting"`) |
| `console` | str | `"NX"` | Console for timing (`"GBA"`, `"NX"`, `"NDS"`, etc.) |
| `tid` | int | `58888` | Trainer ID |
| `sid` | int | `12232` | Secret ID |
| `method` | str | `None` | `"1"`, `"2"`, `"4"`, `"Wild1"`, `"Wild2"`, `"Wild4"`, `"CombinedWild"` |
| `pokemon` | str | `None` | Species ID (e.g. `"1"`) or name (e.g. `"Bulbasaur"`) |
| `nature` | str | `None` | `"Adamant"`, `"Modest"`, etc. or `"Any"` |
| `shiny` | str | `None` | `"Star"`, `"Square"`, `"Any"` |
| `ivs_range` | IVsRange | `None` | Min/max IV bounds per stat |
| `max_time_seconds` | float | `180.0` | Search timeout |

Returns `SearcherResult` with fields: `target_seed`, `method`, `pokemon`, `level`, `pid`, `shiny`, `nature`, `ability`, `ivs`, `hidden_type`, `hidden_power`, `gender`.

### `initial_seed(game, target_seed, count, offset, settings, seed_file) -> List[InitialSeedResult]`

Find button combinations and timing to hit a target 32-bit seed at boot. For FRLG, uses pre-farmed contiguous seed lists; for RSE, uses painting seeds.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `game` | str | `"fr_nx"` | Game version |
| `target_seed` | str | required | 32-bit hex seed (e.g. `"935EFF9E"`) |
| `count` | int | `10` | Number of results |
| `offset` | int | `0` | Advances offset |
| `settings` | GameSettings | `None` | Sound/button mode/seed button/extra button |

Returns `InitialSeedResult` with fields: `seed` (16-bit hex), `advances`, `total_frames`, `total_time`, `seed_time` (ms), `settings`.

### `calibration(game, console, tid, sid, method, seed, advances, settings, seed_bias, advances_bias, offset, ttv_advances_min, ttv_advances_max, overworld_frames, pokemon, ivs_range, ivs_observations, base_stats, seed_file) -> List[CalibrationResult]`

Generate encounter outcomes for a range of initial seeds and advances. Used to calibrate timing by matching observed Pokémon stats against generated results.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `seed` | str | required | 16-bit hex initial seed |
| `advances` | int | required | Center of advances search range |
| `seed_bias` | int | `20` | Search ±N seeds around target |
| `advances_bias` | int | `200` | Search ±N advances around target |
| `ttv_advances_min/max` | int | `0` | Teachy TV advances range |
| `overworld_frames` | int | `0` | NX platform overworld frame offset |
| `pokemon` | str | `None` | Species ID for correct gender ratio |
| `ivs_range` | IVsRange | `None` | IV filter bounds |
| `ivs_observations` | list | `None` | Stat observations for IV calculation |

Returns `CalibrationResult` with fields: `seed`, `advances`, `frames`, `pid`, `shiny`, `nature`, `ability`, `ivs`, `hidden_type`, `hidden_power`, `gender`.

### Helper Types

```python
@dataclass
class GameSettings:
    sound: str = "mono"        # "mono" or "stereo"
    button_mode: str = "a"     # "a" (L=A), "h" (Help), "r" (LR)
    seed_button: str = "a"     # "a" or "start"
    extra_button: str = "none" # "none", "blackout_r", "blackout_l", etc.

@dataclass
class IVs:
    hp: int = 0; attack: int = 0; defense: int = 0
    sp_attack: int = 0; sp_defense: int = 0; speed: int = 0

@dataclass
class IVsRange:
    ivs_lower_bound: IVs
    ivs_upper_bound: IVs
```

## How It Works

### RNG Algorithm

Gen 3 uses a 32-bit LCRNG (Linear Congruential RNG):

```
next_seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
```

Each "advance" consumes one RNG call. Different encounter methods consume different numbers of calls to generate PID, IVs, nature, etc.

### FRLG Initial Seed Manipulation

At boot, the game's initial seed is determined by:
1. **Seed time** — The precise moment (in ms) when the game starts
2. **Button inputs** — Which buttons are held during boot (affects RNG advancement)
3. **Sound setting** — Mono vs. Stereo (affects boot sequence length)

Pre-farmed seed lists (`fr_eng_nx.bin`) map every achievable (seed_time, button_combo) → initial_seed. The `initial_seed()` function searches this list to find which combos produce a given target seed.

### Painting Seeds (RSE)

In Ruby/Sapphire/Emerald, the initial seed can be manipulated via the painting minigame in the Lilycove Museum. The `painting_seeds()` function calculates which painting seeds can reach a target.

## Dependencies

- Python 3.8+
- `requests` (optional, only needed when seed files are not present locally)

### Optional: pybind11 C++ Acceleration

The calibration engine (`calibration_static`, `calibration_wild`) can use a pybind11 C++ module for 2-3x speedup on wild encounters. The module is **self-contained** (no PokeFinder dependency) and falls back to pure Python automatically.

**Pre-built wheels** are available in the [Releases](https://github.com/lincoln-lm/ten-lines/releases) page for:
- Linux x86_64 (manylinux)
- macOS x86_64 / arm64
- Windows x86_64

**Build from source:**

```bash
# Prerequisites: pybind11, a C++ compiler (gcc/clang/msvc)
pip install pybind11

# Build and install
cd src/pybind
python setup.py build_ext --inplace
# This creates calibration_bind*.so in the current directory

# Verify
cd ../..
python verify_pybind.py
```

**Build requirements:**
| OS | Compiler | Notes |
|----|----------|-------|
| Linux | gcc ≥ 4.8 or clang ≥ 3.3 | C++11 required |
| macOS | clang (Xcode) | C++11 required |
| Windows | MSVC 2015+ or MinGW | C++11 required |

## Testing

```bash
# Run unit tests (29 tests)
python -m unittest test_tenlines -v

# Cross-validate pybind11 C++ vs pure Python
python verify_pybind.py

# Cross-validate against C++ known values
python cross_validate.py

# Run performance benchmark
python benchmark/bench_full.py
```

## License

This project is based on [Ten Lines](https://github.com/lincoln-lm/ten-lines) and [PokeFinder](https://github.com/Admiral-Fish/PokeFinder), both licensed under GPLv3.

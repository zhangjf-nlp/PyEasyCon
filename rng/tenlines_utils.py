import math
from typing import List, Tuple, Optional

from .tenlines import (
    SearcherFilter,
    METHOD_1, METHOD_2, METHOD_4,
    painting_seeds, frlg_seeds, load_frlg_seed_data, search_static, search_wild,
    calibration_static, calibration_wild,
    get_contiguous_seed_list,
    HELD_BUTTON_OFFSETS,
    frame_to_ms, ms_to_time_str, hex_seed,
)

# ============================================================
# Data loading: personal info, species/ability names
# ============================================================
_personal_data: Optional[List[dict]] = None
_species_names: Optional[List[str]] = None
_ability_names: Optional[List[str]] = None

def _get_data_dir() -> str:
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources")

def _load_personal() -> List[dict]:
    global _personal_data
    if _personal_data is not None:
        return _personal_data
    import os
    data_dir = _get_data_dir()
    bin_path = os.path.join(data_dir, "Personal", "Gen3", "personal_rsefrlg.bin")
    with open(bin_path, 'rb') as f:
        data = f.read()
    entries = []
    for i in range(0, len(data), 0x1c):
        hp = data[i]; atk = data[i+1]; defense = data[i+2]; spe = data[i+3]
        spa = data[i+4]; spd = data[i+5]
        gender = data[i+0x10]
        ability1 = data[i+0x16]; ability2 = data[i+0x17]
        entries.append({
            "stats": (hp, atk, defense, spa, spd, spe),
            "gender": gender,
            "abilities": (ability1, ability2),
        })
    _personal_data = entries
    return _personal_data

def _load_species_names() -> List[str]:
    global _species_names
    if _species_names is not None:
        return _species_names
    import os
    data_dir = _get_data_dir()
    txt_path = os.path.join(data_dir, "i18n", "en", "species_en.txt")
    with open(txt_path, 'r', encoding='utf-8-sig') as f:
        names = [line.strip() for line in f if line.strip()]
    _species_names = ["Egg"] + names
    return _species_names

def _load_ability_names() -> List[str]:
    global _ability_names
    if _ability_names is not None:
        return _ability_names
    import os
    data_dir = _get_data_dir()
    txt_path = os.path.join(data_dir, "i18n", "en", "abilities_en.txt")
    with open(txt_path, 'r') as f:
        names = [line.strip() for line in f if line.strip()]
    _ability_names = names
    return _ability_names

def get_species_name(species: int) -> str:
    names = _load_species_names()
    return names[species] if 0 <= species < len(names) else str(species)

def get_species_id(name_or_id: str) -> int:
    """Resolve a species name or numeric ID to an integer species ID."""
    try:
        return int(name_or_id)
    except ValueError:
        pass
    names = _load_species_names()
    lower = name_or_id.lower()
    for i, n in enumerate(names):
        if n.lower() == lower:
            return i
    raise ValueError(f"Unknown species: {name_or_id}")

def get_ability_name(ability_id: int) -> str:
    names = _load_ability_names()
    idx = ability_id - 1
    return names[idx] if 0 <= idx < len(names) else str(ability_id)

def get_personal(species: int) -> dict:
    entries = _load_personal()
    return entries[species] if 0 <= species < len(entries) else {"stats": (0,0,0,0,0,0), "gender": 127, "abilities": (0,0)}


def get_seed_time(seed_hex: str, game: str = "fr_nx", game_settings = None) -> int:
    """给定 seed_hex (如 "864A") 和游戏版本，返回 seed_time (毫秒)。
    当 game_settings 包含 Extra Button 时，会自动应用 held_button_offset。
    """
    sm, _ = load_frlg_seed_data(game)
    seed_int = int(seed_hex, 16)

    # 计算 held_button_offset
    offset = 0
    button_mode = 'h'
    if game_settings is not None:
        button_mode = game_settings.button_mode
        extra_button = game_settings.extra_button
        for bm, hb, off in HELD_BUTTON_OFFSETS.get(game, [('h', "none", 0)]):
            if bm == button_mode and hb == extra_button:
                offset = off
                break

    unoffset_seed = (seed_int - offset) & 0xFFFF

    if unoffset_seed not in sm:
        raise KeyError(
            f"seed_hex 0x{seed_hex.upper()} ({seed_int}) 不在 {game} 的种子表中"
            f"（unoffset=0x{unoffset_seed:04X}, offset={offset:+d} via {button_mode}/{game_settings.extra_button if game_settings else 'none'}）"
        )

    # 返回匹配 button_mode 的 entry
    for entry in sm[unoffset_seed]:
        if entry.get('button_mode', 'h') == button_mode:
            return entry['seed_time']
    return sm[unoffset_seed][0]['seed_time']


from modules.species_zh import _SPECIES_EN_TO_ZH


def get_species_zh_name(species_or_name) -> str:
    """获取宝可梦的中文名。接受 species ID (int) 或英文名 (str)。"""
    if isinstance(species_or_name, int):
        en_name = get_species_name(species_or_name)
    else:
        en_name = species_or_name
    if en_name in _SPECIES_EN_TO_ZH:
        return _SPECIES_EN_TO_ZH[en_name]
    return en_name


# 反向映射：中文名 → 英文名
_ZH_TO_EN = {zh: en for en, zh in _SPECIES_EN_TO_ZH.items()}

def get_species_en_name(zh_name: str) -> str:
    """中文名 → 英文名，查找失败返回原值。"""
    return _ZH_TO_EN.get(zh_name, zh_name)


def get_encounter_species_list(location: str, category: str) -> list:
    """返回指定地点和方式的宝可梦 species ID 列表（去重）。"""
    enc = get_encounter(location, category)
    if enc is None:
        return []
    seen = set()
    for slot in enc.get("slots", []):
        sid = slot.get("species")
        if sid is not None:
            seen.add(sid)
    return sorted(seen)


# ============================================================
# Encounter data (wild encounters)
# ============================================================
import json, os
_encounter_cache: dict = {}

_FRLG_MAP_TO_LOCATION = {
    "MAP_ROUTE1": "Route 1", "MAP_ROUTE2": "Route 2", "MAP_ROUTE3": "Route 3",
    "MAP_ROUTE4": "Route 4", "MAP_ROUTE5": "Route 5", "MAP_ROUTE6": "Route 6",
    "MAP_ROUTE7": "Route 7", "MAP_ROUTE8": "Route 8", "MAP_ROUTE9": "Route 9",
    "MAP_ROUTE10": "Route 10", "MAP_ROUTE11": "Route 11", "MAP_ROUTE12": "Route 12",
    "MAP_ROUTE13": "Route 13", "MAP_ROUTE14": "Route 14", "MAP_ROUTE15": "Route 15",
    "MAP_ROUTE16": "Route 16", "MAP_ROUTE17": "Route 17", "MAP_ROUTE18": "Route 18",
    "MAP_ROUTE19": "Route 19", "MAP_ROUTE20": "Route 20", "MAP_ROUTE21": "Route 21",
    "MAP_ROUTE22": "Route 22", "MAP_ROUTE23": "Route 23", "MAP_ROUTE24": "Route 24",
    "MAP_ROUTE25": "Route 25",
    "MAP_VIRIDIAN_FOREST": "Viridian Forest",
    "MAP_MT_MOON_1F": "Mt Moon 1F", "MAP_MT_MOON_B1F": "Mt Moon B1F", "MAP_MT_MOON_B2F": "Mt Moon B2F",
    "MAP_DIGLETTS_CAVE_B1F": "Digletts Cave B1F",
    "MAP_VICTORY_ROAD_1F": "Victory Road 1F/3F", "MAP_VICTORY_ROAD_2F": "Victory Road 2F",
    "MAP_POKEMON_MANSION_1F": "Pokemon Mansion 1F-3F", "MAP_POKEMON_MANSION_B1F": "Pokemon Mansion B1F",
    "MAP_SAFARI_ZONE_CENTER": "Safari Zone Center", "MAP_SAFARI_ZONE_EAST": "Safari Zone East",
    "MAP_SAFARI_ZONE_NORTH": "Safari Zone North", "MAP_SAFARI_ZONE_WEST": "Safari Zone West",
    "MAP_CERULEAN_CAVE_1F": "Cerulean Cave 1F", "MAP_CERULEAN_CAVE_2F": "Cerulean Cave 2F",
    "MAP_CERULEAN_CAVE_B1F": "Cerulean Cave B1F",
    "MAP_ROCK_TUNNEL_1F": "Rock Tunnel 1F", "MAP_ROCK_TUNNEL_B1F": "Rock Tunnel B1F",
    "MAP_SEAFOAM_ISLANDS_1F": "Seafoam Islands 1F", "MAP_SEAFOAM_ISLANDS_B1F": "Seafoam Islands B1F",
    "MAP_SEAFOAM_ISLANDS_B2F": "Seafoam Islands B2F", "MAP_SEAFOAM_ISLANDS_B3F": "Seafoam Islands B3F",
    "MAP_SEAFOAM_ISLANDS_B4F": "Seafoam Islands B4F",
    "MAP_POKEMON_TOWER_3F": "Pokemon Tower 3F", "MAP_POKEMON_TOWER_4F": "Pokemon Tower 4F-5F",
    "MAP_POKEMON_TOWER_6F": "Pokemon Tower 6F", "MAP_POKEMON_TOWER_7F": "Pokemon Tower 7F",
    "MAP_POWER_PLANT": "Power Plant",
    "MAP_MT_EMBER_EXTERIOR": "Mt Ember Exterior",
    "MAP_MT_EMBER_SUMMIT_PATH_1F": "Mt Ember Summit Path 1F/3F",
    "MAP_MT_EMBER_SUMMIT_PATH_2F": "Mt Ember Summit Path 2F",
    "MAP_MT_EMBER_RUBY_PATH_1F": "Mt Ember Ruby Path 1F",
    "MAP_MT_EMBER_RUBY_PATH_B1F": "Mt Ember Ruby Path B1F",
    "MAP_MT_EMBER_RUBY_PATH_B2F": "Mt Ember Ruby Path B2F",
    "MAP_MT_EMBER_RUBY_PATH_B3F": "Mt Ember Ruby Path B3F",
    "MAP_MT_EMBER_RUBY_PATH_B1F_STAIRS": "Mt Ember Ruby Path B1F Stairs",
    "MAP_MT_EMBER_RUBY_PATH_B2F_STAIRS": "Mt Ember Ruby Path B2F Stairs",
    "MAP_THREE_ISLAND_BERRY_FOREST": "Three Island Berry Forest",
    "MAP_FOUR_ISLAND_ICEFALL_CAVE_ENTRANCE": "Four Island Icefall Cave Entrance",
    "MAP_FOUR_ISLAND_ICEFALL_CAVE_1F": "Four Island Icefall Cave 1F/B1F",
    "MAP_FOUR_ISLAND_ICEFALL_CAVE_BACK": "Four Island Icefall Cave Back",
    "MAP_SIX_ISLAND_PATTERN_BUSH": "Six Island Pattern Bush",
    "MAP_FIVE_ISLAND_LOST_CAVE": "Five Island Lost Cave",
    "MAP_ONE_ISLAND_KINDLE_ROAD": "One Island Kindle Road",
    "MAP_ONE_ISLAND_TREASURE_BEACH": "One Island Treasure Beach",
    "MAP_TWO_ISLAND_CAPE_BRINK": "Two Island Cape Brink",
    "MAP_THREE_ISLAND_BOND_BRIDGE": "Three Island Bond Bridge",
    "MAP_FIVE_ISLAND_RESORT_GORGEOUS": "Five Island Resort Gorgeous",
    "MAP_FIVE_ISLAND_WATER_LABYRINTH": "Five Island Water Labyrinth",
    "MAP_FIVE_ISLAND_MEADOW": "Five Island Meadow",
    "MAP_FIVE_ISLAND_MEMORIAL_PILLAR": "Five Island Memorial Pillar",
    "MAP_SIX_ISLAND_OUTCAST_ISLAND": "Six Island Outcast Island",
    "MAP_SIX_ISLAND_GREEN_PATH": "Six Island Green Path",
    "MAP_SIX_ISLAND_WATER_PATH": "Six Island Water Path",
    "MAP_SIX_ISLAND_RUIN_VALLEY": "Six Island Ruin Valley",
    "MAP_SEVEN_ISLAND_TRAINER_TOWER": "Seven Island Trainer Tower",
    "MAP_SEVEN_ISLAND_SEVAULT_CANYON_ENTRANCE": "Seven Island Sevault Canyon Entrance",
    "MAP_SEVEN_ISLAND_SEVAULT_CANYON": "Seven Island Sevault Canyon",
    "MAP_SEVEN_ISLAND_TANOBY_RUINS": "Seven Island Tanoby Ruins",
    "MAP_PALLET_TOWN": "Pallet Town", "MAP_VIRIDIAN_CITY": "Viridian City",
    "MAP_CERULEAN_CITY": "Cerulean City", "MAP_VERMILION_CITY": "Vermilion City",
    "MAP_CELADON_CITY": "Celadon City", "MAP_FUCHSIA_CITY": "Fuchsia City",
    "MAP_CINNABAR_ISLAND": "Cinnabar Island", "MAP_ONE_ISLAND": "One Island",
    "MAP_FOUR_ISLAND": "Four Island", "MAP_FIVE_ISLAND": "Five Island",
    "MAP_SIX_ISLAND_ALTERING_CAVE": "Six Island Altering Cave",
    "MAP_SSANNE_EXTERIOR": "S.S Anne Exterior",
    "MAP_THREE_ISLAND_PORT": "Three Island Port",
    "MAP_FIVE_ISLAND_LOST_CAVE_ITEM_ROOM": "Five Island Lost Cave Item Room",
}

def _load_frlg_encounters() -> dict:
    data_dir = _get_data_dir()
    json_path = os.path.join(data_dir, "EncounterTables", "Gen3", "frlg", "wild_encounters.json")
    with open(json_path, 'r') as f:
        encounters = json.load(f)
    result = {}
    for enc in encounters:
        base = enc.get("base_label", "")
        if "FireRed" not in base:
            continue
        map_name = enc.get("map", "")
        location_name = _FRLG_MAP_TO_LOCATION.get(map_name)
        if location_name is None:
            continue
        for enc_type, key_suffix in [("land_mons", "Grass"), ("water_mons", "Surfing")]:
            section = enc.get(enc_type)
            if section and section.get("encounter_rate", 0) > 0:
                key = (location_name, key_suffix)
                if key not in result:
                    result[key] = {"rate": section["encounter_rate"], "slots": []}
                for slot in section["mons"]:
                    species = slot["species"] & 0x7ff
                    result[key]["slots"].append({
                        "species": species,
                        "min_level": slot["min_level"],
                        "max_level": slot["max_level"],
                    })
        fish = enc.get("fishing_mons")
        if fish and fish.get("encounter_rate", 0) > 0:
            for rod_type, rod_range in [("OldRod", (0,2)), ("GoodRod", (2,5)), ("SuperRod", (5,10))]:
                key = (location_name, rod_type)
                if key not in result:
                    result[key] = {"rate": fish["encounter_rate"], "slots": []}
                for i in range(*rod_range):
                    if i < len(fish["mons"]):
                        slot = fish["mons"][i]
                        result[key]["slots"].append({
                            "species": slot["species"],
                            "min_level": slot["min_level"],
                            "max_level": slot["max_level"],
                        })
    return result

def get_encounter(location: str, category: str) -> Optional[dict]:
    cache_key = (location, category)
    if cache_key in _encounter_cache:
        return _encounter_cache[cache_key]
    all_encounters = _load_frlg_encounters()
    result = all_encounters.get(cache_key)
    _encounter_cache[cache_key] = result
    return result


# ============================================================
# Type definitions (same interface as before)
# ============================================================
from dataclasses import dataclass, field

NATURES = ["Hardy","Lonely","Brave","Adamant","Naughty","Bold","Docile","Relaxed",
           "Impish","Lax","Timid","Hasty","Serious","Jolly","Naive","Modest","Mild",
           "Quiet","Bashful","Rash","Calm","Gentle","Sassy","Careful","Quirky"]
SHININESS = ["None","Star","Square","Star/Square"]
GENDERS = ["M", "F", "-"]
TYPES = ["Fighting","Flying","Poison","Ground","Rock","Bug","Ghost","Steel",
         "Fire","Water","Grass","Electric","Psychic","Ice","Dragon","Dark"]

METHOD_MAP = {
    "Static 1": 1, "Static 2": 3, "Static 4": 4,
    "Wild 1": 5, "Wild 2": 7, "Wild 4": 8,
    "All Wild Methods": 11,
}
METHOD_NAMES = {1: "Static 1", 3: "Static 2", 4: "Static 4",
                5: "Wild 1", 7: "Wild 2", 8: "Wild 4"}

ENCOUNTER_TYPE_MAP = {"Grass": 0, "Surfing": 1, "OldRod": 2, "GoodRod": 3, "SuperRod": 4, "RockSmash": 5}

@dataclass
class IVs:
    hp: int = 0
    attack: int = 0
    defense: int = 0
    sp_attack: int = 0
    sp_defense: int = 0
    speed: int = 0

@dataclass
class IVsRange:
    ivs_lower_bound: IVs = field(default_factory=IVs)
    ivs_upper_bound: IVs = field(default_factory=IVs)

@dataclass
class IVsObservation:
    pokemon: str = ""
    nature: str = ""
    level: int = 0
    hp: int = 0
    attack: int = 0
    defense: int = 0
    sp_attack: int = 0
    sp_defense: int = 0
    speed: int = 0

_SOUND_LABEL_TO_VALUE = {"Mono": "mono", "Stereo": "stereo"}
_SOUND_VALUE_TO_LABEL = {v: k for k, v in _SOUND_LABEL_TO_VALUE.items()}

_BUTTON_MODE_LABEL_TO_VALUE = {"L=A": "a", "Help": "h", "LR": "r"}
_BUTTON_MODE_VALUE_TO_LABEL = {v: k for k, v in _BUTTON_MODE_LABEL_TO_VALUE.items()}

_SEED_BUTTON_LABEL_TO_VALUE = {"A": "a", "Start": "start", "L (L=A)": "l"}
_SEED_BUTTON_VALUE_TO_LABEL = {v: k for k, v in _SEED_BUTTON_LABEL_TO_VALUE.items()}

_EXTRA_BUTTON_LABEL_TO_VALUE = {
    "None": "none", "Startup Select": "startup_select", "Startup A": "startup_a",
    "Blackout R": "blackout_r", "Blackout A": "blackout_a", "Blackout L": "blackout_l",
    "Blackout A+L": "blackout_al",
}
_EXTRA_BUTTON_VALUE_TO_LABEL = {v: k for k, v in _EXTRA_BUTTON_LABEL_TO_VALUE.items()}


@dataclass
class GameSettings:
    sound: str = "mono"
    button_mode: str = "a"
    seed_button: str = "a"
    extra_button: str = "none"

    @property
    def setting_key(self) -> str:
        return f"{self.sound}_{self.button_mode}_{self.seed_button}"

    @classmethod
    def from_string(cls, s: str) -> "GameSettings":
        """
        Parse a display-format string like:
          "Stereo | Help | Seed Button: A | Extra Button: Blackout R"
          "Mono | Help | Seed Button: Start | Extra Button: None"
        """
        parts = [p.strip() for p in s.split("|")]
        if len(parts) != 4:
            raise ValueError(f"Expected 4 parts separated by '|', got {len(parts)}: {s!r}")

        sound_label, button_mode_label = parts[0], parts[1]

        seed_button_raw = parts[2]
        if not seed_button_raw.startswith("Seed Button: "):
            raise ValueError(f"Expected 'Seed Button: ...', got {seed_button_raw!r}")
        seed_button_label = seed_button_raw[len("Seed Button: "):]

        extra_button_raw = parts[3]
        if not extra_button_raw.startswith("Extra Button: "):
            raise ValueError(f"Expected 'Extra Button: ...', got {extra_button_raw!r}")
        extra_button_label = extra_button_raw[len("Extra Button: "):]

        sound = _SOUND_LABEL_TO_VALUE.get(sound_label)
        if sound is None:
            raise ValueError(f"Unknown sound: {sound_label!r}")

        button_mode = _BUTTON_MODE_LABEL_TO_VALUE.get(button_mode_label)
        if button_mode is None:
            raise ValueError(f"Unknown button mode: {button_mode_label!r}")

        seed_button = _SEED_BUTTON_LABEL_TO_VALUE.get(seed_button_label)
        if seed_button is None:
            raise ValueError(f"Unknown seed button: {seed_button_label!r}")

        extra_button = _EXTRA_BUTTON_LABEL_TO_VALUE.get(extra_button_label)
        if extra_button is None:
            raise ValueError(f"Unknown extra button: {extra_button_label!r}")

        return cls(sound=sound, button_mode=button_mode, seed_button=seed_button, extra_button=extra_button)

@dataclass
class SearcherResult:
    target_seed: str = ""
    method: str = ""
    pokemon: str = ""
    level: int = 0
    pid: str = ""
    shiny: str = ""
    nature: str = ""
    ability: str = ""
    ivs: IVs = field(default_factory=IVs)
    hidden_type: str = ""
    hidden_power: int = 0
    gender: str = ""

@dataclass
class InitialSeedResult:
    seed: str = ""
    advances: int = 0
    total_frames: int = 0
    total_time: str = ""
    seed_time: int = 0
    settings: GameSettings = field(default_factory=GameSettings)

@dataclass
class CalibrationResult:
    seed: str = ""
    advances: int = 0
    frames: int = 0
    seed_time: int = 0
    pid: int = 0
    shiny: str = ""
    nature: str = ""
    ability: str = ""
    ivs: IVs = field(default_factory=IVs)
    hidden_type: str = ""
    hidden_power: int = 0
    gender: str = ""
    level: int = 0
    encounter_slot: int = 0
    species: int = 0
    species_name: str = ""
    method: int = 0

    def __str__(self):
        method_name = METHOD_NAMES.get(self.method, f"M{self.method}")
        ivs_str = "/".join(str(getattr(self.ivs, a))
                          for a in ("hp","attack","defense","sp_attack","sp_defense","speed"))
        return (
            f"{self.seed} | {self.seed_time}ms {self.advances} | {method_name} "
            f"{self.frames} {self.encounter_slot}: {self.species_name:<12} "
            f"{self.level:<2} {self.shiny} {self.nature:<8} {self.ability:<10} {ivs_str:<18} {self.hidden_type:<6} {self.gender}"
        )


def parse_method(method_str: str):
    if method_str is None:
        return [METHOD_1], False
    val = METHOD_MAP.get(method_str, 1)
    if val == 11:
        return [METHOD_1, METHOD_2, METHOD_4], True
    if val >= 5:
        return [val - 4], True
    return [val], False


# ============================================================
# Internal helpers
# ============================================================
def _resolve_ability_idx(ability_name: str, species_id: int) -> Optional[int]:
    """Resolve an ability name to slot index (0 or 1) for the given species."""
    if not ability_name or ability_name.lower() == "any":
        return None
    personal = get_personal(species_id)
    for slot, ab_id in enumerate(personal["abilities"]):
        if get_ability_name(ab_id).lower() == ability_name.lower():
            return slot
    return None


def _build_filter(ivs_range, shiny, nature, gender, hidden_type, ability_idx=None):
    filter_iv_min = [0]*6
    filter_iv_max = [31]*6
    if ivs_range is not None:
        filter_iv_min = [ivs_range.ivs_lower_bound.hp, ivs_range.ivs_lower_bound.attack,
                         ivs_range.ivs_lower_bound.defense, ivs_range.ivs_lower_bound.sp_attack,
                         ivs_range.ivs_lower_bound.sp_defense, ivs_range.ivs_lower_bound.speed]
        filter_iv_max = [ivs_range.ivs_upper_bound.hp, ivs_range.ivs_upper_bound.attack,
                         ivs_range.ivs_upper_bound.defense, ivs_range.ivs_upper_bound.sp_attack,
                         ivs_range.ivs_upper_bound.sp_defense, ivs_range.ivs_upper_bound.speed]
    filter_shiny = None
    if shiny and shiny != "Any":
        try: filter_shiny = SHININESS.index(shiny)
        except ValueError: pass
    filter_nature = None
    if nature and nature != "Any":
        try: filter_nature = NATURES.index(nature)
        except ValueError: pass
    filter_gender = None
    if gender and gender != "Any":
        try: filter_gender = GENDERS.index(gender)
        except ValueError: pass
    filter_hidden_type = None
    if hidden_type and hidden_type != "Any":
        try: filter_hidden_type = TYPES.index(hidden_type)
        except ValueError: pass
    return filter_iv_min, filter_iv_max, filter_shiny, filter_nature, filter_gender, filter_hidden_type, ability_idx


def _enrich_slots_with_gender(encounter_data):
    """Add gender_ratio to each slot from personal data if missing."""
    if encounter_data is None:
        return None
    slots = encounter_data.get("slots", [])
    for slot in slots:
        if "gender_ratio" not in slot:
            personal = get_personal(slot.get("species", 0))
            slot["gender_ratio"] = personal["gender"]
    return encounter_data


def _make_searcher_result(g, target_seed, method_name, species_name, level):
    ivs = g['ivs']
    personal = get_personal(g.get('species', 0))
    ability_id = personal["abilities"][g['ability']]
    return SearcherResult(
        target_seed=hex_seed(target_seed, 32),
        method=method_name,
        pokemon=species_name,
        level=level,
        pid=format(g['pid'], '08X'),
        shiny=SHININESS[g['shiny']],
        nature=NATURES[g['nature']],
        ability=get_ability_name(ability_id),
        ivs=IVs(hp=ivs[0], attack=ivs[1], defense=ivs[2],
                sp_attack=ivs[3], sp_defense=ivs[4], speed=ivs[5]),
        hidden_type=TYPES[g['hidden_type']],
        hidden_power=g['hidden_power'],
        gender=GENDERS[g['gender']],
    )


def _make_calibration_result(g, seed):
    ivs = g['ivs']
    personal = get_personal(g.get('species', 0))
    ability_id = personal["abilities"][g['ability']]
    return CalibrationResult(
        seed=hex_seed(seed, 16),
        advances=g['advances'],
        frames=g['advances'],
        seed_time=g.get('seed_time', 0),
        pid=g['pid'],
        shiny=SHININESS[g['shiny']],
        nature=NATURES[g['nature']],
        ability=get_ability_name(ability_id),
        ivs=IVs(hp=ivs[0], attack=ivs[1], defense=ivs[2],
                sp_attack=ivs[3], sp_defense=ivs[4], speed=ivs[5]),
        hidden_type=TYPES[g['hidden_type']],
        hidden_power=g['hidden_power'],
        gender=GENDERS[g['gender']],
        level=g.get('level', 0),
        encounter_slot=g.get('encounter_slot', 0),
        species=g.get('species', 0),
        species_name=get_species_name(g.get('species', 0)),
        method=g.get('method', 0),
    )


# ============================================================
# Searcher
# ============================================================
def searcher(
    game: str = "fr_nx",
    console: str = None,
    tid: int = 58888,
    sid: int = 12232,
    method: str = None,
    category: str = None,
    location: str = None,
    pokemon: str = None,
    shiny: str = None,
    nature: str = None,
    gender: str = None,
    hidden_type: str = None,
    ivs_range: IVsRange = None,
    max_time_seconds: float = 180.0,
) -> List[SearcherResult]:
    if console is None:
        console = "NX2" if game.endswith("nx2") else "NX"
    tsv = tid ^ sid
    max_time_ms = max_time_seconds * 1000
    is_frlg = not game.endswith("painting")
    seed_data = None
    if is_frlg:
        seed_data = load_frlg_seed_data(game)
    methods, is_wild = parse_method(method)
    filter_iv_min, filter_iv_max, filter_shiny, filter_nature, filter_gender, filter_hidden_type, _ = \
        _build_filter(ivs_range, shiny, nature, gender, hidden_type)
    encounter_data = None
    encounter_type = 0
    if is_wild:
        encounter_data = get_encounter(location, category)
        if encounter_data is None:
            raise ValueError(f"No encounter data for location={location} category={category}")
        _enrich_slots_with_gender(encounter_data)
        encounter_type = ENCOUNTER_TYPE_MAP.get(category, 0)
    filter_obj = SearcherFilter(
        natures={filter_nature} if filter_nature is not None else None,
        shiny=filter_shiny, gender=filter_gender, hp_type=filter_hidden_type,
        iv_min=filter_iv_min, iv_max=filter_iv_max,
    )
    results = []
    for m in methods:
        if is_wild:
            gen = search_wild(filter_iv_min, filter_iv_max, m, tsv, encounter_data["slots"],
                              encounter_type=encounter_type, filter_obj=filter_obj)
        else:
            gen = search_static(filter_iv_min, filter_iv_max, m, tsv,
                                gender_ratio=127, filter_obj=filter_obj)
        for g in gen:
            target_seed = g['seed']
            init_results = initial_seed(
                game=game, console=console,
                target_seed=hex_seed(target_seed, 32),
                result_count=1, offset=0)
            if not init_results:
                continue
            ir = init_results[0]
            total_ms = frame_to_ms(ir.total_frames, console)
            if total_ms > max_time_ms:
                continue
            method_name = METHOD_NAMES.get(m + (4 if is_wild else 0), f"Method {m}")
            species_name = get_species_name(g.get('species', 0)) if is_wild else ""
            level = g.get('level', 0) if is_wild else 0
            results.append(_make_searcher_result(g, target_seed, method_name, species_name, level))
    return results


# ============================================================
# Initial seed
# ============================================================
def initial_seed(
    game: str = "fr_nx",
    console: str = None,
    target_seed: str = None,
    result_count: int = 10,
    offset: int = 0,
) -> List[InitialSeedResult]:
    if console is None:
        console = "NX2" if game.endswith("nx2") else "NX"
    if target_seed is None:
        raise ValueError("target_seed is required")
    target = int(target_seed, 16)
    is_frlg = not game.endswith("painting")
    seed_data = None
    if is_frlg:
        seed_data = load_frlg_seed_data(game)
    if is_frlg:
        raw = frlg_seeds(target, result_count, offset, game, ttv_frames_out=0, seed_data=seed_data)
        results = []
        for r in raw:
            advances = r["advances"]
            seed_time = r["seed_time"]
            iseed = r["initial_seed"]
            key_str = r["key"]
            # parse settings from key: "setting_key_held_button"
            parts = key_str.rsplit("_", 1) if key_str else ("", "none")
            if len(parts) == 2 and parts[0]:
                setting_key = parts[0]
                held_button = parts[1]
                # extract button_mode from setting key: e.g. "mono_a" -> "a"
                bm_parts = setting_key.rsplit("_", 1)
                button_mode = bm_parts[-1] if len(bm_parts) > 1 else "a"
            else:
                button_mode = "a"
                held_button = "none"
            total_frames = (seed_time / 16) + advances if seed_time else advances
            total_ms = frame_to_ms(total_frames, console)
            results.append(InitialSeedResult(
                seed=hex_seed(iseed, 16),
                advances=advances,
                total_frames=round(total_frames),
                total_time=ms_to_time_str(total_ms),
                seed_time=seed_time,
                settings=GameSettings(button_mode=button_mode, extra_button=held_button),
            ))
        return results
    else:
        raw = painting_seeds(target, result_count, offset)
        results = []
        for r in raw:
            advances = r["advances"]
            iseed = r["initial_seed"]
            seed_time = r["seed_time"]
            total_frames = iseed + advances
            total_ms = frame_to_ms(total_frames, console)
            results.append(InitialSeedResult(
                seed=hex_seed(iseed, 16),
                advances=advances,
                total_frames=round(total_frames),
                total_time=ms_to_time_str(total_ms),
                seed_time=seed_time,
            ))
        return results


# ============================================================
# IV Calculator
# ============================================================
def iv_calculator(
    ivs_observations: List[IVsObservation],
    base_stats: Tuple[int, int, int, int, int, int] = None,
) -> IVsRange:
    if not ivs_observations or base_stats is None:
        return IVsRange(
            ivs_lower_bound=IVs(0, 0, 0, 0, 0, 0),
            ivs_upper_bound=IVs(31, 31, 31, 31, 31, 31),
        )
    all_possible = [{i for i in range(32)} for _ in range(6)]
    nature_map = {n: i for i, n in enumerate(NATURES)}
    # stat_idx: 1=atk 2=def 3=spa 4=spd 5=spe; -1=neutral (no effect)
    # nature order: Hardy Lonely Brave Adamant Naughty Bold Docile Relaxed Impish Lax
    #               Timid Hasty Serious Jolly Naive Modest Mild Quiet Bashful Rash
    #               Calm Gentle Sassy Careful Quirky
    nature_boost  = [  -1,  1,  1,  1,  1,  2, -1,  2,  2,  2,
                        5,  5, -1,  5,  5,  3,  3,  3, -1,  3,
                        4,  4,  4,  4, -1]
    nature_reduce = [  -1,  2,  5,  3,  4,  1, -1,  5,  3,  4,
                        1,  2, -1,  3,  4,  1,  2,  5, -1,  4,
                        1,  2,  5,  3, -1]
    for obs in ivs_observations:
        nature_idx = nature_map.get(obs.nature.strip().title(), -1)
        boost_stat  = nature_boost[nature_idx]  if 0 <= nature_idx < 25 else -1
        reduce_stat = nature_reduce[nature_idx] if 0 <= nature_idx < 25 else -1
        observed = [obs.hp, obs.attack, obs.defense, obs.sp_attack, obs.sp_defense, obs.speed]
        possible_for_obs = [set() for _ in range(6)]
        for stat_idx in range(6):
            base = base_stats[stat_idx]
            lv = obs.level
            for iv in range(32):
                if stat_idx == 0:
                    stat = math.floor((2 * base + iv) * lv / 100) + lv + 10
                else:
                    stat = math.floor((2 * base + iv) * lv / 100) + 5
                    if stat_idx == boost_stat:
                        stat = math.floor(stat * 1.1)
                    elif stat_idx == reduce_stat:
                        stat = math.floor(stat * 0.9)
                if stat == observed[stat_idx]:
                    possible_for_obs[stat_idx].add(iv)
        for stat_idx in range(6):
            if possible_for_obs[stat_idx]:
                all_possible[stat_idx] &= possible_for_obs[stat_idx]
    lower = IVs()
    upper = IVs()
    stat_attrs = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
    for i, attr in enumerate(stat_attrs):
        if all_possible[i]:
            setattr(lower, attr, min(all_possible[i]))
            setattr(upper, attr, max(all_possible[i]))
        else:
            setattr(lower, attr, 32)
            setattr(upper, attr, 0)
    return IVsRange(ivs_lower_bound=lower, ivs_upper_bound=upper)


# ============================================================
# Calibration
# ============================================================
def calibration(
    game: str = "fr_nx",
    console: str = None,
    tid: int = 58888,
    sid: int = 12232,
    method: str = None,
    category: str = None,
    location: str = None,
    pokemon: str = None,
    shiny: str = None,
    nature: str = None,
    gender: str = None,
    ability: str = None,
    seed: str = None,
    advances: int = None,
    settings: GameSettings = None,
    seed_bias: int = 20,
    advances_bias: int = 200,
    offset: int = 0,
    ttv_advances_min: int = 0,
    ttv_advances_max: int = 0,
    overworld_frames: int = 0,
    ivs_observations: List[IVsObservation] = None,
    ivs_range: IVsRange = None,
    level: int = None,
) -> List[CalibrationResult]:
    if console is None:
        console = "NX2" if game.endswith("nx2") else "NX"
    if seed is None:
        raise ValueError("seed is required")
    if pokemon is None:
        raise ValueError("pokemon is required")
    species_id = get_species_id(pokemon)  # raises ValueError if not found
    personal = get_personal(species_id)
    base_stats: Tuple[int, int, int, int, int, int] = personal["stats"]
    gender_ratio: int = personal["gender"]
    ability_idx = _resolve_ability_idx(ability, species_id) if ability else None
    # 转换为实际的 ability ID（pybind 需要 ID 而非 slot index）
    # ability 过滤在 calibration 中不可靠，始终通配
    _ = ability_idx  # 保留变量但不用
    ability_id = None
    if ivs_range is None and ivs_observations is not None:
        ivs_range = iv_calculator(ivs_observations, base_stats)
    target_initial_seed = int(seed, 16)
    tsv = tid ^ sid
    is_frlg = not game.endswith("painting")
    seed_data = None
    if is_frlg:
        seed_data = load_frlg_seed_data(game)
    # build contiguous seed list centered around target
    if is_frlg and seed_data:
        setting_key = f"{settings.sound}_{settings.button_mode}_{settings.seed_button}" if settings else "mono_h_a"
        seed_list = get_contiguous_seed_list(seed_data, setting_key, game, settings.extra_button if settings else "none")
    else:
        seed_list = [{"initial_seed": s, "seed_time": s * 16} for s in range(0x10000)]
        target_initial_seed = target_initial_seed & 0xFFFF
    # find target index
    target_idx = 0
    for i, entry in enumerate(seed_list):
        if entry["initial_seed"] == target_initial_seed:
            target_idx = i
            break
    start_idx = max(0, target_idx - seed_bias)
    end_idx = min(len(seed_list), target_idx + seed_bias + 1)
    search_seeds = seed_list[start_idx:end_idx]
    # advances range
    min_adv = max(0, advances - advances_bias) if advances is not None else 0
    max_adv = (advances + advances_bias) if advances is not None else 200
    # apply overworld_frames offset (NX platform)
    if overworld_frames > 0:
        min_adv = max(0, min_adv - overworld_frames)
        max_adv = max(0, max_adv - overworld_frames)
    methods, is_wild = parse_method(method)
    encounter_data = None
    encounter_type = 0
    matching_slots = None
    if is_wild:
        encounter_data = get_encounter(location, category)
        if encounter_data is None:
            raise ValueError(f"No encounter data for location={location} category={category}")
        _enrich_slots_with_gender(encounter_data)
        encounter_type = ENCOUNTER_TYPE_MAP.get(category, 0)
        # 计算目标宝可梦对应的 encounter slot 编号
        if species_id:
            slots_list = encounter_data.get("slots", [])
            matching = [i for i, slot in enumerate(slots_list) if slot.get("species") == species_id]
            if matching:
                matching_slots = matching
    filter_iv_min, filter_iv_max, filter_shiny, filter_nature, filter_gender, _, _ = \
        _build_filter(ivs_range, shiny, nature, gender, None, ability_id)
    filter_obj = SearcherFilter(
        natures={filter_nature} if filter_nature is not None else None,
        shiny=filter_shiny, gender=filter_gender,
        iv_min=filter_iv_min, iv_max=filter_iv_max,
        ability=ability_id,
        slots=matching_slots,
    )
    ttv_range = (ttv_advances_min, ttv_advances_max)
    results = []
    for entry in search_seeds:
        s = entry["initial_seed"]
        st = entry["seed_time"]
        seeds_entry = [{"initial_seed": s, "seed_time": st}]
        for m in methods:
            if is_wild:
                level_min = level if level is not None else 0
                level_max = level if level is not None else 0
                raw = calibration_wild(
                    seeds_entry, min_adv, max_adv, offset, m, tsv,
                    encounter_data["slots"], encounter_type=encounter_type, filter_obj=filter_obj,
                    ttv_advances_range=ttv_range, level_min=level_min, level_max=level_max)
            else:
                raw = calibration_static(
                    seeds_entry, min_adv, max_adv, offset, m, tsv,
                    gender_ratio=gender_ratio, filter_obj=filter_obj,
                    ttv_advances_range=ttv_range)
            for g in raw:
                results.append(_make_calibration_result(g, s))
    return results

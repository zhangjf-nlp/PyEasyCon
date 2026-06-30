/**
 * pybind11 bindings for Gen3 calibration (StaticGenerator3).
 * Self-contained implementation - no dependency on PokeFinderCore.
 *
 * Returns results as numpy structured arrays for zero-copy performance.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

#include <cstdint>
#include <vector>
#include <array>
#include <tuple>
#include <cstring>

namespace py = pybind11;

// ============================================================
// PokeRNG: LCRNG with add=0x6073, mult=0x41C64E6D
// ============================================================
class PokeRNG {
public:
    static constexpr uint32_t ADD = 0x6073;
    static constexpr uint32_t MULT = 0x41C64E6D;

    PokeRNG(uint32_t seed) : seed_(seed) {}
    PokeRNG(uint32_t seed, uint32_t advances) : seed_(seed) { jump(advances); }

    uint32_t next() {
        seed_ = seed_ * MULT + ADD;
        return seed_;
    }

    uint16_t nextUShort() {
        return next() >> 16;
    }

    uint32_t getSeed() const { return seed_; }

    void jump(uint32_t advances) {
        static const uint32_t jump_mult[32] = {
            0x41C64E6Du, 0xC2A29A69u, 0xEE067F11u, 0xCFDDDF21u,
            0x5F748241u, 0x8B2E1481u, 0x76006901u, 0x1711D201u,
            0xBE67A401u, 0xDDDF4801u, 0x3FFE9001u, 0x90FD2001u,
            0x65FA4001u, 0xDBF48001u, 0xF7E90001u, 0xEFD20001u,
            0xDFA40001u, 0xBF480001u, 0x7E900001u, 0xFD200001u,
            0xFA400001u, 0xF4800001u, 0xE9000001u, 0xD2000001u,
            0xA4000001u, 0x48000001u, 0x90000001u, 0x20000001u,
            0x40000001u, 0x80000001u, 0x00000001u, 0x00000001u
        };
        static const uint32_t jump_add[32] = {
            0x00006073u, 0xE97E7B6Au, 0x31B0DDE4u, 0x67DBB608u,
            0xCBA72510u, 0x1D29AE20u, 0xBA84EC40u, 0x79F01880u,
            0x08793100u, 0x6B566200u, 0x803CC400u, 0xA6B98800u,
            0xE6731000u, 0x30E62000u, 0xF1CC4000u, 0x23988000u,
            0x47310000u, 0x8E620000u, 0x1CC40000u, 0x39880000u,
            0x73100000u, 0xE6200000u, 0xCC400000u, 0x98800000u,
            0x31000000u, 0x62000000u, 0xC4000000u, 0x88000000u,
            0x10000000u, 0x20000000u, 0x40000000u, 0x80000000u
        };

        for (int i = 0; advances; advances >>= 1, i++) {
            if (advances & 1) {
                seed_ = seed_ * jump_mult[i] + jump_add[i];
            }
        }
    }

private:
    uint32_t seed_;
};

// ============================================================
// Hidden Power calculation
// ============================================================
static constexpr uint8_t HP_ORDER[6] = {0, 1, 2, 5, 3, 4};

inline uint8_t calc_hidden_power(const std::array<uint8_t, 6>& ivs) {
    uint8_t h = 0;
    for (int i = 0; i < 6; i++) {
        h |= (ivs[HP_ORDER[i]] & 1) << i;
    }
    return h * 15 / 63;
}

inline uint8_t calc_hidden_power_strength(const std::array<uint8_t, 6>& ivs) {
    uint8_t p = 0;
    for (int i = 0; i < 6; i++) {
        p |= ((ivs[HP_ORDER[i]] >> 1) & 1) << i;
    }
    return 30 + (p * 40 / 63);
}

// ============================================================
// Shiny calculation
// ============================================================
inline uint8_t calc_shiny(uint32_t pid, uint16_t tsv) {
    uint16_t psv = (pid >> 16) ^ (pid & 0xFFFF);
    if (tsv == psv) return 2;
    if ((tsv ^ psv) < 8) return 1;
    return 0;
}

// ============================================================
// Gender calculation
// ============================================================
inline uint8_t calc_gender(uint32_t pid, uint8_t gender_ratio) {
    switch (gender_ratio) {
        case 255: return 2;
        case 254: return 1;
        case 0:   return 0;
        default:  return (pid & 255) < gender_ratio ? 1 : 0;
    }
}

// ============================================================
// Filter check
// ============================================================
inline bool check_filter(
    const std::array<uint8_t, 6>& ivs,
    uint8_t ability, uint8_t gender, uint8_t nature, uint8_t shiny,
    const std::array<uint8_t, 6>& iv_min,
    const std::array<uint8_t, 6>& iv_max,
    uint8_t filter_shiny, uint8_t filter_gender,
    int filter_nature, uint8_t filter_ability)
{
    for (int i = 0; i < 6; i++) {
        if (ivs[i] < iv_min[i] || ivs[i] > iv_max[i]) return false;
    }
    if (filter_shiny != 255 && !(filter_shiny & shiny)) return false;
    if (filter_gender != 255 && filter_gender != gender) return false;
    if (filter_nature != -1 && filter_nature != static_cast<int>(nature)) return false;
    if (filter_ability != 255 && filter_ability != ability) return false;
    return true;
}

// ============================================================
// Numpy structured array dtype for results
// ============================================================
// Static fields: advances(u4), pid(u4), iv0-u1..iv5-u1, ability-u1, gender-u1,
//         nature-u1, shiny-u1, hidden_power-u1, hidden_power_strength-u1,
//         initial_seed-u4, seed_time-u4, ttv_advances-u4
// Wild adds: level-u1, encounter_slot-u1, species-u2, form-u1, method-u1

// Packed struct for direct memory write into numpy array
#pragma pack(push, 1)
struct ResultRow {
    uint32_t advances;
    uint32_t pid;
    uint8_t iv0, iv1, iv2, iv3, iv4, iv5;
    uint8_t ability;
    uint8_t gender;
    uint8_t nature;
    uint8_t shiny;
    uint8_t hidden_power;
    uint8_t hidden_power_strength;
    uint32_t initial_seed;
    uint32_t seed_time;
    uint32_t ttv_advances;
    // wild-only fields
    uint8_t level;
    uint8_t encounter_slot;
    uint16_t species;
    uint8_t form;
    uint8_t method;
};
#pragma pack(pop)

// ============================================================
// Static generate that writes directly to numpy array
// ============================================================
inline uint32_t static_generate_to_array(
    uint32_t seed,
    uint32_t initial_advances,
    uint32_t max_advances,
    uint32_t offset,
    int method,
    uint16_t tsv,
    uint8_t gender_ratio,
    bool bugged_roamer,
    const std::array<uint8_t, 6>& iv_min,
    const std::array<uint8_t, 6>& iv_max,
    uint8_t filter_shiny,
    uint8_t filter_gender,
    int filter_nature,
    uint8_t filter_ability,
    uint32_t initial_seed_val,
    uint32_t seed_time_val,
    uint32_t ttv_adv,
    ResultRow* out,
    uint32_t out_capacity)
{
    uint32_t out_idx = 0;
    PokeRNG rng(seed, initial_advances + offset);

    for (uint32_t cnt = 0; cnt <= max_advances && out_idx < out_capacity; cnt++, rng.next()) {
        PokeRNG go(rng);

        uint32_t pid = go.nextUShort();
        pid |= go.nextUShort() << 16;

        uint16_t iv1 = bugged_roamer ? (go.nextUShort() & 0xFF) : go.nextUShort();
        if (method == 4) {
            go.next();
        }
        uint16_t iv2 = bugged_roamer ? 0 : go.nextUShort();

        std::array<uint8_t, 6> ivs;
        ivs[0] = iv1 & 31;
        ivs[1] = (iv1 >> 5) & 31;
        ivs[2] = (iv1 >> 10) & 31;
        ivs[3] = (iv2 >> 5) & 31;
        ivs[4] = (iv2 >> 10) & 31;
        ivs[5] = iv2 & 31;

        uint8_t ability = pid & 1;
        uint8_t gender = calc_gender(pid, gender_ratio);
        uint8_t nature = pid % 25;
        uint8_t shiny = calc_shiny(pid, tsv);

        if (check_filter(ivs, ability, gender, nature, shiny,
                         iv_min, iv_max, filter_shiny, filter_gender,
                         filter_nature, filter_ability)) {
            uint8_t hp = calc_hidden_power(ivs);
            uint8_t hp_str = calc_hidden_power_strength(ivs);

            ResultRow& row = out[out_idx++];
            row.advances = initial_advances + cnt;
            row.pid = pid;
            row.iv0 = ivs[0]; row.iv1 = ivs[1]; row.iv2 = ivs[2];
            row.iv3 = ivs[3]; row.iv4 = ivs[4]; row.iv5 = ivs[5];
            row.ability = ability;
            row.gender = gender;
            row.nature = nature;
            row.shiny = shiny;
            row.hidden_power = hp;
            row.hidden_power_strength = hp_str;
            row.initial_seed = initial_seed_val;
            row.seed_time = seed_time_val;
            row.ttv_advances = ttv_adv;
        }
    }

    return out_idx;
}

// ============================================================
// Python-callable check_seeds_static - returns numpy array
// ============================================================
py::array check_seeds_static(
    const py::list& seeds,
    const std::tuple<uint32_t, uint32_t>& advances_range,
    const std::tuple<uint32_t, uint32_t>& ttv_range,
    uint32_t offset,
    uint16_t trainer_id,
    uint16_t secret_id,
    int method,
    uint8_t shininess,
    int nature,
    uint8_t gender,
    const py::list& iv_ranges,
    uint8_t gender_ratio,
    bool bugged_roamer,
    uint8_t filter_ability)
{
    uint16_t tsv = (trainer_id ^ secret_id) & 0xFFFF;

    // Build IV ranges
    std::array<uint8_t, 6> iv_min, iv_max;
    for (int i = 0; i < 6; i++) {
        auto range = iv_ranges[i].cast<std::tuple<uint8_t, uint8_t>>();
        iv_min[i] = std::get<0>(range);
        iv_max[i] = std::get<1>(range);
    }

    uint32_t starting_final_frame = std::get<0>(advances_range);
    uint32_t ending_final_frame = std::get<1>(advances_range);
    uint32_t initial_ttv = std::get<0>(ttv_range);
    uint32_t ending_ttv = std::min(std::get<1>(ttv_range), ending_final_frame);

    // Pre-calculate max possible results for pre-allocation
    size_t n_seeds = seeds.size();
    uint32_t ttv_count = ending_ttv - initial_ttv + 1;
    uint32_t max_adv_per_seed = ending_final_frame - starting_final_frame + 1;
    size_t max_results = n_seeds * ttv_count * max_adv_per_seed;

    // Allocate numpy array - use full dtype with wild fields for uniform layout
    auto dtype = py::dtype("u4,u4,u1,u1,u1,u1,u1,u1,u1,u1,u1,u1,u1,u1,u4,u4,u4,u1,u1,u2,u1,u1");
    auto result = py::array(dtype, max_results);
    auto buf = result.request();
    ResultRow* out = static_cast<ResultRow*>(buf.ptr);

    // Zero-initialize the buffer so wild-only fields are 0
    std::memset(buf.ptr, 0, max_results * sizeof(ResultRow));

    uint32_t total_results = 0;

    for (auto& seed_entry : seeds) {
        auto seed_tuple = seed_entry.cast<std::tuple<uint32_t, uint32_t>>();
        uint32_t initial_seed = static_cast<uint32_t>(std::get<0>(seed_tuple));
        uint32_t seed_time = static_cast<uint32_t>(std::get<1>(seed_tuple));

        for (uint32_t ttv_adv = initial_ttv; ttv_adv <= ending_ttv; ttv_adv++) {
            uint32_t start_adv = starting_final_frame > ttv_adv ?
                starting_final_frame - ttv_adv : 0;
            uint32_t end_adv = ending_final_frame > ttv_adv ?
                ending_final_frame - ttv_adv : 0;
            uint32_t max_adv = end_adv - start_adv;

            uint32_t remaining = static_cast<uint32_t>(max_results - total_results);
            uint32_t n = static_generate_to_array(
                initial_seed,
                start_adv + ttv_adv * 313,
                max_adv,
                offset,
                method,
                tsv,
                gender_ratio,
                bugged_roamer,
                iv_min, iv_max,
                shininess, gender, nature, filter_ability,
                initial_seed, seed_time, ttv_adv,
                out + total_results,
                remaining
            );
            total_results += n;
        }
    }

    // Resize to actual results
    result.resize({total_results});
    return result;
}

// ============================================================
// Encounter slot tables (Gen3 hSlot)
// ============================================================
static const std::vector<uint8_t>& get_slot_table(int encounter_type) {
    static const std::vector<uint8_t> grass = {
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,
        2,2,2,2,2,2,2,2,2,2,
        3,3,3,3,3,3,3,3,3,3,
        4,4,4,4,4,4,4,4,4,4,
        5,5,5,5,5,5,5,5,5,5,
        6,6,6,6,6,
        7,7,7,7,7,
        8,8,8,8,
        9,9,9,9,
        10,
        11
    };
    static const std::vector<uint8_t> surfing = {
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,
        1,1,1,1,1,1,1,1,1,1,
        2,2,2,2,2,
        3,3,3,3,
        4
    };
    static const std::vector<uint8_t> old_rod = {
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,
        1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1
    };
    // water1: {60, 80, 100} → 0*60 + 1*20 + 2*20
    static const std::vector<uint8_t> good_rod = {
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,
        2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,
    };
    static const std::vector<uint8_t> super_rod = {
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,
        1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,
        2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,
        3,3,3,3,
        4
    };
    static const std::vector<uint8_t> empty;

    switch (encounter_type) {
        case 0: return grass;
        case 1: return surfing;
        case 2: return old_rod;
        case 3: return good_rod;
        case 4: return super_rod;
        case 5: return surfing;  // RockSmash uses surfing table
        default: return empty;
    }
}

inline uint8_t hslot(uint16_t rand_val, int encounter_type) {
    const auto& table = get_slot_table(encounter_type);
    if (table.empty()) return 0;
    return table[rand_val % table.size()];
}

// ============================================================
// Wild generate that writes directly to numpy array
// ============================================================
inline uint32_t wild_generate_to_array(
    uint32_t seed,
    uint32_t initial_advances,
    uint32_t max_advances,
    uint32_t offset,
    int method,
    uint16_t tsv,
    int encounter_type,
    const std::vector<std::tuple<uint16_t, uint8_t, uint8_t, uint8_t, uint8_t>>& slot_info,
    const std::array<uint8_t, 6>& iv_min,
    const std::array<uint8_t, 6>& iv_max,
    uint8_t filter_shiny,
    uint8_t filter_gender,
    int filter_nature,
    uint8_t filter_ability,
    uint8_t filter_level,
    uint32_t initial_seed_val,
    uint32_t seed_time_val,
    uint32_t ttv_adv,
    int method_encoding,
    ResultRow* out,
    uint32_t out_capacity)
{
    uint32_t out_idx = 0;
    PokeRNG rng(seed, initial_advances + offset);

    for (uint32_t cnt = 0; cnt <= max_advances && out_idx < out_capacity; cnt++, rng.next()) {
        PokeRNG go(rng);

        // encounterSlot = hSlot(go.nextUShort(100), encounter)
        uint8_t enc_slot = hslot(go.nextUShort() % 100, encounter_type);
        if (enc_slot >= slot_info.size()) continue;

        uint16_t species = std::get<0>(slot_info[enc_slot]);
        uint8_t form = std::get<1>(slot_info[enc_slot]);
        uint8_t min_lv = std::get<2>(slot_info[enc_slot]);
        uint8_t max_lv = std::get<3>(slot_info[enc_slot]);
        uint8_t gender_ratio = std::get<4>(slot_info[enc_slot]);

        // level = area.calculateLevel(encounterSlot, go.nextUShort())
        uint8_t level = min_lv + (go.nextUShort() % (max_lv - min_lv + 1));
        if (filter_level != 0 && filter_level != level) continue;

        // nature = go.nextUShort(25)
        uint8_t nature_val = go.nextUShort() % 25;

        // do { pid = ... } while (pid % 25 != nature)
        uint32_t pid;
        do {
            uint32_t pid_low = go.nextUShort();
            uint32_t pid_high = go.nextUShort();
            pid = (pid_high << 16) | pid_low;
        } while (pid % 25 != nature_val);

        // if (method == Method2) go.next()
        if (method == 3) {
            go.next();
        }

        uint16_t iv1 = go.nextUShort();
        if (method == 4) {
            go.next();
        }
        uint16_t iv2 = go.nextUShort();

        std::array<uint8_t, 6> ivs;
        ivs[0] = iv1 & 31;
        ivs[1] = (iv1 >> 5) & 31;
        ivs[2] = (iv1 >> 10) & 31;
        ivs[3] = (iv2 >> 5) & 31;
        ivs[4] = (iv2 >> 10) & 31;
        ivs[5] = iv2 & 31;

        uint8_t ability = pid & 1;
        uint8_t gender = calc_gender(pid, gender_ratio);
        uint8_t shiny = calc_shiny(pid, tsv);

        if (check_filter(ivs, ability, gender, nature_val, shiny,
                         iv_min, iv_max, filter_shiny, filter_gender,
                         filter_nature, filter_ability)) {
            uint8_t hp = calc_hidden_power(ivs);
            uint8_t hp_str = calc_hidden_power_strength(ivs);

            ResultRow& row = out[out_idx++];
            row.advances = initial_advances + cnt;
            row.pid = pid;
            row.iv0 = ivs[0]; row.iv1 = ivs[1]; row.iv2 = ivs[2];
            row.iv3 = ivs[3]; row.iv4 = ivs[4]; row.iv5 = ivs[5];
            row.ability = ability;
            row.gender = gender;
            row.nature = nature_val;
            row.shiny = shiny;
            row.hidden_power = hp;
            row.hidden_power_strength = hp_str;
            row.initial_seed = initial_seed_val;
            row.seed_time = seed_time_val;
            row.ttv_advances = ttv_adv;
            row.level = level;
            row.encounter_slot = enc_slot;
            row.species = species;
            row.form = form;
            row.method = static_cast<uint8_t>(method_encoding);
        }
    }

    return out_idx;
}

// ============================================================
// Python-callable check_seeds_wild - returns numpy array
// ============================================================
py::array check_seeds_wild(
    const py::list& seeds,
    const std::tuple<uint32_t, uint32_t>& advances_range,
    const std::tuple<uint32_t, uint32_t>& ttv_range,
    uint32_t offset,
    uint16_t trainer_id,
    uint16_t secret_id,
    int method,
    uint8_t shininess,
    int nature,
    uint8_t gender,
    const py::list& iv_ranges,
    int encounter_type,
    const py::list& encounter_slots,
    uint8_t filter_ability,
    uint8_t filter_level)
{
    uint16_t tsv = (trainer_id ^ secret_id) & 0xFFFF;

    // Build IV ranges
    std::array<uint8_t, 6> iv_min, iv_max;
    for (int i = 0; i < 6; i++) {
        auto range = iv_ranges[i].cast<std::tuple<uint8_t, uint8_t>>();
        iv_min[i] = std::get<0>(range);
        iv_max[i] = std::get<1>(range);
    }

    // Parse encounter slots info
    std::vector<std::tuple<uint16_t, uint8_t, uint8_t, uint8_t, uint8_t>> slot_info;
    for (auto& slot : encounter_slots) {
        auto s = slot.cast<py::dict>();
        uint16_t species = s["species"].cast<uint16_t>();
        uint8_t form = s.contains("form") ? s["form"].cast<uint8_t>() : 0;
        uint8_t min_lv = s.contains("min_level") ? s["min_level"].cast<uint8_t>() : 1;
        uint8_t max_lv = s.contains("max_level") ? s["max_level"].cast<uint8_t>() : 1;
        uint8_t gr = s.contains("gender_ratio") ? s["gender_ratio"].cast<uint8_t>() : 127;
        slot_info.push_back(std::make_tuple(species, form, min_lv, max_lv, gr));
    }

    uint32_t starting_final_frame = std::get<0>(advances_range);
    uint32_t ending_final_frame = std::get<1>(advances_range);
    uint32_t initial_ttv = std::get<0>(ttv_range);
    uint32_t ending_ttv = std::min(std::get<1>(ttv_range), ending_final_frame);

    // For wild, method can be a combination (1|2|4) meaning try all three
    // Python uses METHOD_1=1, METHOD_2=3, METHOD_4=4
    std::vector<int> methods;
    if (method == 7 || method == (1 | 2 | 4)) {
        methods = {1, 3, 4};
    } else {
        methods = {method};
    }

    // Pre-calculate max possible results
    size_t n_seeds = seeds.size();
    uint32_t ttv_count = ending_ttv - initial_ttv + 1;
    uint32_t max_adv_per_seed = ending_final_frame - starting_final_frame + 1;
    size_t max_results = n_seeds * ttv_count * methods.size() * max_adv_per_seed;

    // Allocate numpy array - same dtype as static plus wild fields
    auto dtype = py::dtype("u4,u4,u1,u1,u1,u1,u1,u1,u1,u1,u1,u1,u1,u1,u4,u4,u4,u1,u1,u2,u1,u1");
    auto result = py::array(dtype, max_results);
    auto buf = result.request();
    ResultRow* out = static_cast<ResultRow*>(buf.ptr);

    uint32_t total_results = 0;

    for (auto& seed_entry : seeds) {
        auto seed_tuple = seed_entry.cast<std::tuple<uint32_t, uint32_t>>();
        uint32_t initial_seed = static_cast<uint32_t>(std::get<0>(seed_tuple));
        uint32_t seed_time = static_cast<uint32_t>(std::get<1>(seed_tuple));

        for (uint32_t ttv_adv = initial_ttv; ttv_adv <= ending_ttv; ttv_adv++) {
            uint32_t start_adv = starting_final_frame > ttv_adv ?
                starting_final_frame - ttv_adv : 0;
            uint32_t end_adv = ending_final_frame > ttv_adv ?
                ending_final_frame - ttv_adv : 0;
            uint32_t max_adv = end_adv - start_adv;

            for (int m : methods) {
                uint32_t remaining = static_cast<uint32_t>(max_results - total_results);
                uint32_t n = wild_generate_to_array(
                    initial_seed,
                    start_adv + ttv_adv * 313,
                    max_adv,
                    offset,
                    m,
                    tsv,
                    encounter_type,
                    slot_info,
                    iv_min, iv_max,
                    shininess, gender, nature, filter_ability, filter_level,
                    initial_seed, seed_time, ttv_adv,
                    m + 4,  // wild method encoding = static method + 4
                    out + total_results,
                    remaining
                );
                total_results += n;
            }
        }
    }

    // Resize to actual results
    result.resize({total_results});
    return result;
}

PYBIND11_MODULE(calibration_bind, m) {
    m.doc() = "Gen3 calibration (StaticGenerator3) - pybind11 accelerated (standalone)";

    m.def("check_seeds_static", &check_seeds_static,
          py::arg("seeds"),
          py::arg("advances_range"),
          py::arg("ttv_range"),
          py::arg("offset"),
          py::arg("trainer_id"),
          py::arg("secret_id"),
          py::arg("method"),
          py::arg("shininess"),
          py::arg("nature"),
          py::arg("gender"),
          py::arg("iv_ranges"),
          py::arg("gender_ratio"),
          py::arg("bugged_roamer"),
          py::arg("filter_ability"),
          "Generate static encounter states for calibration. Returns numpy structured array.");

    m.def("check_seeds_wild", &check_seeds_wild,
          py::arg("seeds"),
          py::arg("advances_range"),
          py::arg("ttv_range"),
          py::arg("offset"),
          py::arg("trainer_id"),
          py::arg("secret_id"),
          py::arg("method"),
          py::arg("shininess"),
          py::arg("nature"),
          py::arg("gender"),
          py::arg("iv_ranges"),
          py::arg("encounter_type"),
          py::arg("encounter_slots"),
          py::arg("filter_ability"),
          py::arg("filter_level"),
          "Generate wild encounter states for calibration. Returns numpy structured array.");
}

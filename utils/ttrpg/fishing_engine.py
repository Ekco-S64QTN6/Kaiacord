"""
fishing_engine.py — Aethelgard Fishing Mechanics
==================================================
Deterministic catch resolution. All randomness is here, no UI.
Called by fishing_handler.py.
"""
import secrets
import os
import json
from datetime import date, datetime
from typing import Optional

from utils.ttrpg.fishing import (
    FISH, BAIT, POLES, CATEGORY_RARITY_WEIGHT, CATEGORY_WEIGHT_BONUS,
    get_available_fish, get_time_of_day,
)

FISHING_RECORDS_PATH = os.path.join("memory", "ttrpg", "fishing_records.json")

# ── Rarity roll thresholds ────────────────────────────────────────────────────
# These are base thresholds BEFORE bait/pole bonuses.
# Higher roll → rarer category selected from available pool.
RARITY_THRESHOLDS = {
    "mythic":    999,    # 999-1000 (0.2% base)
    "legendary": 995,    # 995-998 (0.4% base)
    "epic":      985,    # 985-994 (1.0% base)
    "rare":      950,    # 950-984 (3.5% base)
    "uncommon":  800,    # 800-949 (15% base)
    "common":      0,    # 0-799 (80% base)
}


def roll_catch(
    bait_key: str,
    pole_key: str,
    season: str,
    time_of_day: str,
    conditions: list,
) -> tuple[str, dict, float]:
    """
    Resolve a fishing catch.
    Returns (fish_key, fish_data, weight_in_lbs) or raises ValueError if miss.

    Miss rate: 20% base, reduced by pole and bait bonuses.
    """
    bait = BAIT.get(bait_key, BAIT["earthworm"])
    pole = POLES.get(pole_key, POLES["birchwood_rod"])

    # Miss check
    miss_base = 20
    miss_base -= min(10, (bait["catch_bonus"] // 5))
    miss_base -= min(5, (pole["catch_bonus"] // 8))
    if "blessed" in conditions:
        miss_base -= 5
    miss_base = max(5, miss_base)

    if secrets.randbelow(100) < miss_base:
        raise ValueError("miss")

    # Rarity roll (1-1000)
    raw = secrets.randbelow(1000) + 1
    roll = raw + bait["catch_bonus"] + pole["catch_bonus"]
    if "blessed" in conditions:
        roll += 20
    if "lucky" in conditions:
        roll += 10
    roll = min(roll, 1000)

    # Select rarity category
    selected_cat = "common"
    for cat, threshold in RARITY_THRESHOLDS.items():
        if roll >= threshold:
            selected_cat = cat
            break

    # Enforce bait ceiling
    from utils.ttrpg.fishing import BAIT_RARITY_CEILING
    ceiling = BAIT_RARITY_CEILING.get(bait_key, list(RARITY_THRESHOLDS.keys()))
    if selected_cat not in ceiling:
        # Walk down to the highest available cat
        cat_order = ["mythic", "legendary", "epic", "rare", "uncommon", "common"]
        for fallback in cat_order:
            if fallback in ceiling:
                selected_cat = fallback
                break

    # Pick a fish from available pool
    available = get_available_fish(season, time_of_day, bait_key)
    pool = available.get(selected_cat, [])

    # If bait preference matches, weight those fish double
    weighted_pool: list[tuple[str, dict, int]] = []
    bait_pref_cats = bait.get("preferred_cats", [])
    for fish_key, fish_data in pool:
        weight = 2 if fish_data["category"] in bait_pref_cats else 1
        # Additional weight if fish prefers this bait
        if bait_key in fish_data.get("bait_pref", []):
            weight += 2
        weighted_pool.append((fish_key, fish_data, weight))

    if not weighted_pool:
        # Absolute fallback to any common fish
        fallback_pool = [(k, v, 1) for k, v in FISH.items() if v["category"] == "common"]
        weighted_pool = fallback_pool

    total_w = sum(w for _, _, w in weighted_pool)
    r = secrets.randbelow(total_w)
    cumulative = 0
    chosen_key, chosen_fish = weighted_pool[0][0], weighted_pool[0][1]
    for fish_key, fish_data, w in weighted_pool:
        cumulative += w
        if r < cumulative:
            chosen_key = fish_key
            chosen_fish = fish_data
            break

    # Roll weight
    min_w, max_w = chosen_fish["weight_range"]
    weight_roll = secrets.randbelow(1000) / 1000.0  # 0.0-1.0
    # Bias toward lower weights (exponential distribution feel)
    weight_roll = weight_roll ** 1.5
    fish_weight = min_w + (max_w - min_w) * weight_roll
    fish_weight = round(fish_weight, 2)

    return chosen_key, chosen_fish, fish_weight


def calculate_catch_value(fish_key: str, fish_weight: float, cha_mod: int = 0) -> int:
    """Calculate the gil sell value for a single caught fish."""
    fish = FISH.get(fish_key)
    if not fish:
        return 1
    min_w, max_w = fish["weight_range"]
    weight_pct = (fish_weight - min_w) / max(max_w - min_w, 0.01)
    weight_pct = max(0.0, min(1.0, weight_pct))
    bonus_mult = CATEGORY_WEIGHT_BONUS.get(fish["category"], 0.30)
    cha_bonus = 1.0 + (max(0, cha_mod) * 0.02)
    value = int(fish["sell_value"] * (1.0 + bonus_mult * weight_pct) * cha_bonus)
    
    # Tiered economic caps to prevent "dragon loot" fishing
    cat = fish.get("category", "common")
    if cat == "mythic":
        value = min(250, value)
    elif cat == "legendary":
        value = min(200, value)
    elif cat == "epic":
        value = min(150, value)
    else:
        # Keep Rare/Uncommon/Common natural (usually 2-95g)
        pass

    return max(1, value)


def add_to_fishing_bag(sheet: dict, fish_key: str, fish_weight: float, value: int) -> dict:
    """Add a caught fish to the player's fishing bag."""
    bag = sheet.setdefault("fishing_bag", {})
    if fish_key not in bag:
        bag[fish_key] = []
    bag[fish_key].append({"weight": fish_weight, "value": value})

    # Update stats
    stats = sheet.setdefault("fishing_stats", {})
    stats["total_caught"] = stats.get("total_caught", 0) + 1
    stats["total_weight"] = round(stats.get("total_weight", 0.0) + fish_weight, 2)
    stats["total_value_caught"] = stats.get("total_value_caught", 0) + value

    # Species counts
    species = stats.setdefault("species_caught", {})
    species[fish_key] = species.get(fish_key, 0) + 1

    # Personal record
    records = stats.setdefault("personal_records", {})
    if fish_key not in records or fish_weight > records[fish_key]["weight"]:
        records[fish_key] = {
            "weight": fish_weight,
            "date": date.today().isoformat(),
        }

    return sheet


def sell_fishing_bag(sheet: dict, cha_mod: int = 0) -> tuple[int, int, str]:
    """
    Sell all fish in the bag.
    Returns (total_gil, fish_count, summary_line).
    """
    bag = sheet.get("fishing_bag", {})
    if not bag:
        return 0, 0, "Your bag is empty."

    total_gil = 0
    fish_count = 0
    lines = []

    for fish_key, catches in bag.items():
        fish = FISH.get(fish_key)
        name = fish["name"] if fish else fish_key
        count = len(catches)
        subtotal = sum(c["value"] for c in catches)
        total_gil += subtotal
        fish_count += count
        if count > 0:
            lines.append(f"{name} ×{count} → {subtotal}g")

    sheet["fishing_bag"] = {}
    sheet["gil"] = sheet.get("gil", 0) + total_gil
    sheet.setdefault("fishing_stats", {})["total_sold"] = (
        sheet["fishing_stats"].get("total_sold", 0) + total_gil
    )

    summary = "\n".join(lines[:15])  # cap Discord display
    if len(lines) > 15:
        summary += f"\n*...and {len(lines) - 15} more species*"

    return total_gil, fish_count, summary


def get_bag_summary(sheet: dict) -> tuple[int, int, list[str]]:
    """
    Summarize bag contents.
    Returns (total_fish, total_estimated_value, list_of_lines).
    """
    bag = sheet.get("fishing_bag", {})
    total_fish = 0
    total_val = 0
    lines = []
    for fish_key, catches in bag.items():
        fish = FISH.get(fish_key)
        name = fish["name"] if fish else fish_key
        cat = fish["category"] if fish else "common"
        count = len(catches)
        subtotal = sum(c["value"] for c in catches)
        best_weight = max(c["weight"] for c in catches) if catches else 0
        total_fish += count
        total_val += subtotal
        cat_emoji = {
            "common": "⚪", "uncommon": "🟢", "rare": "🔵",
            "epic": "🟣", "legendary": "🟡", "mythic": "🔴",
        }.get(cat, "⚪")
        lines.append(f"{cat_emoji} {name} ×{count} (best: {best_weight:.2f} lbs · {subtotal}g)")
    return total_fish, total_val, lines


# ── Global fishing records I/O ────────────────────────────────────────────────

def _ensure_records() -> dict:
    if not os.path.exists(FISHING_RECORDS_PATH):
        return {"world_records": {}, "species_totals": {}, "angler_totals": {}}
    try:
        with open(FISHING_RECORDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"world_records": {}, "species_totals": {}, "angler_totals": {}}


def _save_records(records: dict):
    os.makedirs(os.path.dirname(FISHING_RECORDS_PATH), exist_ok=True)
    tmp = FISHING_RECORDS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    os.replace(tmp, FISHING_RECORDS_PATH)


def update_world_records(
    fish_key: str,
    fish_weight: float,
    char_name: str,
    uid: str,
) -> bool:
    """
    Check and update world record for a fish species.
    Returns True if this is a new world record.
    """
    records = _ensure_records()
    current = records["world_records"].get(fish_key, {})
    is_record = not current or fish_weight > current.get("weight", 0.0)
    if is_record:
        records["world_records"][fish_key] = {
            "weight": fish_weight,
            "holder": char_name,
            "uid": uid,
            "date": date.today().isoformat(),
        }
    # Update species totals
    records["species_totals"][fish_key] = records["species_totals"].get(fish_key, 0) + 1
    # Update angler totals
    records["angler_totals"][uid] = records["angler_totals"].get(uid, 0) + 1
    _save_records(records)
    return is_record


def get_world_records() -> dict:
    return _ensure_records()


def get_fishing_leaderboard(mode: str = "total") -> list[tuple[str, str, int | float]]:
    """
    mode = "total"    → top anglers by fish count
    mode = "heaviest" → top individual catches across all species
    Returns list of (char_name_or_fish_name, detail_str, value).
    """
    records = _ensure_records()
    if mode == "total":
        sorted_anglers = sorted(
            records["angler_totals"].items(), key=lambda x: x[1], reverse=True
        )
        return [(uid, f"{count} fish", count) for uid, count in sorted_anglers[:10]]
    elif mode == "heaviest":
        all_records = []
        for fish_key, rec in records["world_records"].items():
            fish = FISH.get(fish_key)
            name = fish["name"] if fish else fish_key
            all_records.append((
                name,
                f"{rec['weight']:.2f} lbs by {rec['holder']}",
                rec["weight"],
            ))
        return sorted(all_records, key=lambda x: x[2], reverse=True)[:10]
    return []


def get_fishing_stats_embed_fields(sheet: dict) -> list[tuple[str, str]]:
    """Return list of (field_name, field_value) for a player fishing stats embed."""
    stats = sheet.get("fishing_stats", {})
    total_caught = stats.get("total_caught", 0)
    total_weight = stats.get("total_weight", 0.0)
    total_sold = stats.get("total_sold", 0)
    species_caught = stats.get("species_caught", {})
    num_species = len(species_caught)

    # Best personal catch
    personal = stats.get("personal_records", {})
    if personal:
        best_key = max(
            personal, key=lambda k: FISH.get(k, {}).get("sell_value", 0) * personal[k].get("weight", 0)
        )
        best_fish = FISH.get(best_key, {})
        best_name = best_fish.get("name", best_key)
        best_rec = personal[best_key]
        best_str = f"{best_name} — {best_rec['weight']:.2f} lbs ({best_rec['date']})"
    else:
        best_str = "None yet"

    current_pole = stats.get("pole", "birchwood_rod")
    current_bait = stats.get("bait", "earthworm")
    bait_count = stats.get("bait_count", 0)

    pole_name = POLES.get(current_pole, {}).get("name", current_pole)
    bait_name = BAIT.get(current_bait, {}).get("name", current_bait)

    return [
        ("🎣 Pole", pole_name),
        ("🪱 Bait", f"{bait_name} (×{bait_count})"),
        ("🐟 Total Caught", str(total_caught)),
        ("⚖️ Total Weight", f"{total_weight:.1f} lbs"),
        ("🗂️ Species Found", str(num_species)),
        ("💰 Total Sold", f"{total_sold}g"),
        ("🏆 Best Catch", best_str),
    ]


def get_bite_wait_time(pole_key: str) -> int:
    """Return seconds to wait before bite attempt."""
    pole = POLES.get(pole_key, POLES["birchwood_rod"])
    base = secrets.randbelow(6) + 5  # 5-10 seconds
    reduced = base - pole.get("bite_time_reduction", 0)
    return max(3, reduced)


def get_reel_window(pole_key: str) -> int:
    """Return seconds player has to click Reel."""
    pole = POLES.get(pole_key, POLES["birchwood_rod"])
    return pole.get("reel_window", 12)

"""
Player Housing System — Aethelgard
Inspired by Ultima Online housing progression.
"""

HOUSING_DISTRICT_KEY = "housing_district"
PLAYER_PLOT_PREFIX = "plot_"

# ── Housing Tiers ─────────────────────────────────────────────────────────────
# Each tier unlocks more furniture slots, farming plots, and pet slots.

from utils.ttrpg.record_scan import ScanFailure, ScanReport, log_scan_failures


HOUSING_TIERS = {
    "hut": {
        "name": "Wattle Hut",
        "cost": 1000,
        "upgrade_from": None,
        "desc": "A single-room wattle-and-daub hut on the outskirts of Oakhaven. It keeps the rain out. Mostly.",
        "emoji": "🛖",
        "furniture_slots": 5,
        "farming_plots": 1,
        "pet_slots": 1,
        "level_required": 1,
        "flavor": "The deed is warm from the clerk's hands. It's yours now. Small, but yours.",
    },
    "cottage": {
        "name": "Stone Cottage",
        "cost": 5000,
        "upgrade_from": "hut",
        "desc": "A proper stone cottage with a hearth, two rooms, and a garden wall.",
        "emoji": "🏡",
        "furniture_slots": 12,
        "farming_plots": 3,
        "pet_slots": 2,
        "level_required": 4,
        "flavor": "The mason finishes the last stone. The hearth draws well. This is a home now.",
    },
    "longhouse": {
        "name": "Oak Longhouse",
        "cost": 15000,
        "upgrade_from": "cottage",
        "desc": "A grand longhouse of seasoned oak. Wide enough to entertain. Strong enough to outlast you.",
        "emoji": "🏠",
        "furniture_slots": 25,
        "farming_plots": 6,
        "pet_slots": 3,
        "level_required": 6,
        "flavor": "The longhouse stands. The Whisperwood can see it from the treeline.",
    },
    "keep": {
        "name": "Oakhaven Keep",
        "cost": 40000,
        "upgrade_from": "longhouse",
        "desc": "Stone walls. Iron gates. A tower with a view of the Whisperwood canopy. This is legacy.",
        "emoji": "🏰",
        "furniture_slots": 50,
        "farming_plots": 12,
        "pet_slots": 5,
        "level_required": 8,
        "flavor": "The final stone is set at dusk. Elder Elara came to see it. She said nothing. That was the point.",
    },
}

TIER_ORDER = ["hut", "cottage", "longhouse", "keep"]

# ── Default Housing Sheet ──────────────────────────────────────────────────────

def default_housing_sheet(user_id: str, character_name: str, tier: str = "hut") -> dict:
    import time
    from datetime import date
    return {
        "user_id": user_id,
        "character_name": character_name,
        "tier": tier,
        "furniture": [],          # list of placed furniture keys
        "farming": {
            "plots": [],          # list of plot dicts: {slot, crop, planted_date, watered_today, stage}
        },
        "pets": [],               # list of pet dicts: {key, name, fed_today, days_owned}
        "visitors_today": [],     # user_ids who visited today (future: player shops)
        "house_name": f"{character_name}'s {HOUSING_TIERS[tier]['name']}",
        "created_at": time.time(),
        "last_updated": time.time(),
        "last_farm_reset": date.today().isoformat(),
    }

# ── Persistence ────────────────────────────────────────────────────────────────

import os, json
import threading

HOUSING_DIR = os.path.join("memory", "ttrpg", "housing")
_lock = threading.Lock()

def _housing_path(user_id: str) -> str:
    os.makedirs(HOUSING_DIR, exist_ok=True)
    return os.path.join(HOUSING_DIR, f"{user_id}.json")

def load_housing(user_id: str) -> dict | None:
    """Read one housing record without applying daily resets or writing it.

    Daily farm/pet resets are explicit in-memory mutations coordinated by
    character_manager.load(), which owns the player's lock and commits any
    changed character + housing snapshots through the recovery journal.
    """
    p = _housing_path(str(user_id))
    with _lock:
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            home = json.load(f)
        if not isinstance(home, dict):
            raise ValueError("housing root must be a JSON object")
        stored_uid = home.get("user_id")
        if stored_uid is None:
            # The requested filename is authoritative for legacy housing.
            home["user_id"] = str(user_id)
        elif str(stored_uid) != str(user_id):
            raise ValueError(
                f"housing user_id {stored_uid!r} does not match requested owner {user_id!r}"
            )
        return home


def apply_daily_housing_reset(housing: dict, *, today: str | None = None) -> bool:
    """Apply the daily farm/pet transition in memory, once per calendar day.

    This function performs no I/O. The caller persists a changed housing
    snapshot under the owner's action lock, paired with the character sheet
    when invoked from character_manager.load().
    """
    if not isinstance(housing, dict):
        return False
    from datetime import date

    reset_day = today or date.today().isoformat()
    if housing.get("last_farm_reset") == reset_day:
        return False

    from utils.ttrpg.farming import reset_daily_farm
    from utils.ttrpg.pets import reset_daily_pets
    reset_daily_farm(housing, today=reset_day)
    reset_daily_pets(housing)
    return True

def _write_housing(user_id: str, text: str) -> None:
    from utils.core.atomic_write import write_atomic
    with _lock:
        write_atomic(_housing_path(user_id), text)


def _serialise_housing(housing: dict) -> str:
    import time
    housing["last_updated"] = time.time()
    return json.dumps(housing, indent=2)


def save_housing(housing: dict) -> None:
    _write_housing(str(housing["user_id"]), _serialise_housing(housing))

async def load_housing_async(user_id: str) -> dict | None:
    import asyncio
    return await asyncio.to_thread(load_housing, user_id)

async def save_housing_async(housing: dict) -> None:
    import asyncio
    # Serialised on the caller's thread; the dict is live.
    await asyncio.to_thread(_write_housing, str(housing["user_id"]), _serialise_housing(housing))

def load_all_housing_report() -> ScanReport:
    """Load valid homes and expose damaged or mismatched per-player files."""
    records: list[dict] = []
    failures: list[ScanFailure] = []
    try:
        os.makedirs(HOUSING_DIR, exist_ok=True)
        with _lock:
            filenames = sorted(os.listdir(HOUSING_DIR))
    except OSError as exc:
        return ScanReport(
            [],
            [ScanFailure(HOUSING_DIR, None, f"{type(exc).__name__}: {exc}")],
        )

    for fname in filenames:
        if not fname.endswith(".json"):
            continue
        path = os.path.join(HOUSING_DIR, fname)
        owner_id = fname[:-5]
        try:
            with open(path, "r", encoding="utf-8") as handle:
                home = json.load(handle)
            if not isinstance(home, dict):
                raise ValueError("housing root must be a JSON object")
            stored_uid = home.get("user_id")
            if stored_uid is None:
                home["user_id"] = owner_id
            elif str(stored_uid) != owner_id:
                raise ValueError(
                    f"housing user_id {stored_uid!r} does not match filename owner {owner_id!r}"
                )
            farming = home.get("farming")
            if farming is not None:
                if not isinstance(farming, dict):
                    raise ValueError("farming must be a JSON object")
                plots = farming.get("plots", [])
                if not isinstance(plots, list) or any(
                    not isinstance(plot, dict) for plot in plots
                ):
                    raise ValueError("farming.plots must be an array of JSON objects")
            pets = home.get("pets", [])
            if not isinstance(pets, list) or any(not isinstance(pet, dict) for pet in pets):
                raise ValueError("pets must be an array of JSON objects")
            records.append(home)
        except FileNotFoundError:
            # A concurrent delete after directory enumeration is not corruption.
            continue
        except Exception as exc:
            failures.append(
                ScanFailure(path, owner_id, f"{type(exc).__name__}: {str(exc)[:180]}")
            )

    report = ScanReport(records, failures)
    log_scan_failures("housing records", report)
    return report


def load_all_housing() -> list[dict]:
    """Compatibility list API; skipped housing files are logged with exact paths."""
    return load_all_housing_report().records

def get_tier_data(tier_key: str) -> dict:
    return HOUSING_TIERS.get(tier_key, HOUSING_TIERS["hut"])

def get_next_tier(current_tier: str) -> str | None:
    idx = TIER_ORDER.index(current_tier)
    if idx + 1 < len(TIER_ORDER):
        return TIER_ORDER[idx + 1]
    return None

def can_afford_upgrade(sheet: dict, housing: dict) -> tuple[bool, str]:
    next_t = get_next_tier(housing["tier"])
    if not next_t:
        return False, "Your estate is already at maximum tier."
    tier_data = HOUSING_TIERS[next_t]
    if sheet["level"] < tier_data["level_required"]:
        return False, f"Requires Level {tier_data['level_required']}."
    if sheet["gil"] < tier_data["cost"]:
        return False, f"Costs {tier_data['cost']}g. You have {sheet['gil']}g."
    return True, ""

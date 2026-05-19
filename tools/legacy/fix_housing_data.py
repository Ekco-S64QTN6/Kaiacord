"""
Housing Data Fix Script — 2026-04-03
Fixes:
  1. Duplicate pets (refunds gil for removed duplicates)
  2. Stale last_farm_reset (clears to trigger proper reset on next load)
"""

import json
import os

HOUSING_DIR = "memory/ttrpg/housing"
CHAR_DIR = "memory/ttrpg/characters"

PET_COSTS = {
    "cat": 200,
    "chocobo_chick": 500,
    "tonberry_companion": 1500,
    "whisperwood_sprite": 800,
    "moogle": 2000,
    "aeridor_construct": 5000,
}

def main():
    if not os.path.isdir(HOUSING_DIR):
        print(f"Housing directory not found: {HOUSING_DIR}")
        return

    housing_files = [f for f in os.listdir(HOUSING_DIR) if f.endswith(".json")]
    print(f"Scanning {len(housing_files)} housing files...\n")

    total_dupes_removed = 0
    total_gil_refunded = 0
    total_farm_resets = 0

    for fname in housing_files:
        hpath = os.path.join(HOUSING_DIR, fname)
        with open(hpath, "r") as f:
            housing = json.load(f)

        user_id = fname.replace(".json", "")
        changes = []

        # --- 1. Duplicate Pet Fix ---
        pets = housing.get("pets", [])
        if pets:
            seen_keys = set()
            unique_pets = []
            removed_pets = []
            for p in pets:
                if p["key"] in seen_keys:
                    removed_pets.append(p)
                else:
                    seen_keys.add(p["key"])
                    unique_pets.append(p)

            if removed_pets:
                housing["pets"] = unique_pets
                total_refund = 0
                for rp in removed_pets:
                    cost = PET_COSTS.get(rp["key"], 0)
                    total_refund += cost

                # Refund gil to character sheet
                char_path = os.path.join(CHAR_DIR, f"{user_id}.json")
                if os.path.exists(char_path) and total_refund > 0:
                    with open(char_path, "r") as f:
                        sheet = json.load(f)
                    sheet["gil"] = sheet.get("gil", 0) + total_refund
                    with open(char_path, "w") as f:
                        json.dump(sheet, f, indent=2)
                    changes.append(f"  PETS: Removed {len(removed_pets)} duplicate(s), refunded {total_refund}g")
                else:
                    changes.append(f"  PETS: Removed {len(removed_pets)} duplicate(s), no char sheet found for refund")

                total_dupes_removed += len(removed_pets)
                total_gil_refunded += total_refund

        # --- 2. Farm Reset Fix ---
        if housing.get("last_farm_reset", "") != "":
            housing["last_farm_reset"] = ""
            total_farm_resets += 1
            changes.append(f"  FARM: Cleared last_farm_reset (was '{housing.get('last_farm_reset', '')}')")

        # --- Save ---
        if changes:
            with open(hpath, "w") as f:
                json.dump(housing, f, indent=2)
            print(f"[FIXED] {fname}:")
            for c in changes:
                print(c)
        else:
            print(f"[OK]    {fname}")

    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Files scanned:       {len(housing_files)}")
    print(f"  Duplicate pets removed: {total_dupes_removed}")
    print(f"  Gil refunded:        {total_gil_refunded}g")
    print(f"  Farm resets cleared: {total_farm_resets}")


if __name__ == "__main__":
    main()

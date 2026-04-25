#!/usr/bin/env python3
"""
One-off maintenance script: purge deprecated status-effect consumables
from all player character sheets.

Removes: antidote, panacea, gold_needle, maidens_kiss, soft

Uses atomic writes (.tmp + os.replace()) per project convention.
"""
import os
import json

CHAR_DIR = os.path.join(os.path.dirname(__file__), "memory", "ttrpg", "characters")
DEPRECATED_ITEMS = {"antidote", "panacea", "gold_needle", "maidens_kiss", "soft"}


def purge():
    if not os.path.isdir(CHAR_DIR):
        print(f"Character directory not found: {CHAR_DIR}")
        return

    files = [f for f in os.listdir(CHAR_DIR) if f.endswith(".json")]
    total_removed = 0

    for fname in sorted(files):
        path = os.path.join(CHAR_DIR, fname)
        with open(path) as f:
            sheet = json.load(f)

        char_name = sheet.get("character_name", fname)
        inventory = sheet.get("inventory", [])
        removed = [item for item in inventory if item in DEPRECATED_ITEMS]

        if not removed:
            print(f"  {char_name:20s} — clean")
            continue

        sheet["inventory"] = [item for item in inventory if item not in DEPRECATED_ITEMS]
        total_removed += len(removed)

        # Atomic write
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(sheet, f, indent=2)
        os.replace(tmp, path)

        print(f"  {char_name:20s} — removed {len(removed)}: {', '.join(removed)}")

    print(f"\nDone. {total_removed} deprecated item(s) purged across {len(files)} character sheet(s).")


if __name__ == "__main__":
    purge()

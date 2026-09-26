"""Town projects: gil pooled into Oakhaven's walls.

The second endgame sink. Players donate at the town square; when the fund
reaches PROJECT_COST the walls are reinforced for a week, and every noon raid
in that week is fought with +2 defence for the defenders. The cost is shared,
so it asks the server's bankrolls — hundreds of thousands of gil with nothing
to buy — to spend together on something everyone who plays benefits from.
"""
from __future__ import annotations

import time
from typing import Tuple

PROJECT_COST = 250_000
FORTIFIED_S = 7 * 86400
RAID_DEF_BONUS = 2
DONATE_AT = "oakhaven"


def raid_def_bonus(wstate: dict, now: float | None = None) -> int:
    """+2 defence in noon raids while the walls are reinforced."""
    return RAID_DEF_BONUS if float(wstate.get("fortified_until") or 0) > (now or time.time()) else 0


def donate(sheet: dict, wstate: dict, amount: int, now: float | None = None) -> Tuple[bool, str]:
    """Move gil from the sheet into the town fund; reinforce the walls when it
    reaches the cost. Mutates both dicts; the caller saves them."""
    now = now or time.time()
    if amount <= 0:
        return False, "Donate how much?"
    if sheet.get("gil", 0) < amount:
        return False, f"You have {sheet.get('gil', 0):,}g on hand."
    sheet["gil"] -= amount
    fund = int(wstate.get("town_fund") or 0) + amount
    donors = wstate.setdefault("town_donors", {})
    name = sheet.get("character_name", "someone")
    donors[name] = int(donors.get(name, 0)) + amount
    text = f"**{name}** gives {amount:,}g to the walls."
    if fund >= PROJECT_COST:
        fund -= PROJECT_COST
        start = max(now, float(wstate.get("fortified_until") or 0))
        wstate["fortified_until"] = start + FORTIFIED_S
        days = round((wstate["fortified_until"] - now) / 86400)
        text += (f"\n\n🧱 **The walls are reinforced.** For the next {days} days, defenders fight the "
                 f"noon raids with +{RAID_DEF_BONUS} defence.")
    wstate["town_fund"] = fund
    text += f"\nFund: {fund:,} / {PROJECT_COST:,}g."
    return True, text


def status(wstate: dict, now: float | None = None) -> str:
    now = now or time.time()
    fund = int(wstate.get("town_fund") or 0)
    lines = [f"Fund toward reinforcing the walls: **{fund:,} / {PROJECT_COST:,}g**."]
    until = float(wstate.get("fortified_until") or 0)
    if until > now:
        lines.append(f"🧱 Reinforced for {max(1, round((until - now) / 86400))} more days: +{RAID_DEF_BONUS} defence in raids.")
    top = sorted((wstate.get("town_donors") or {}).items(), key=lambda kv: -kv[1])[:5]
    if top:
        lines.append("Top givers: " + ", ".join(f"{n} {v:,}g" for n, v in top))
    return "\n".join(lines)

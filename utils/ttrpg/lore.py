"""
lore.py — The Lore Codex: collectible pages of Aethelgard's history.

Pages are found in rare forest events, on rare monster variants and in noon
events. They live on the sheet as ``lore_pages`` (a list of page IDs); a set
completed for the first time pays its reward once and is recorded in
``lore_sets_done``. Everything here is a pure in-memory mutation of a sheet the
caller already holds under the player's lock and saves through its own path.
"""
import secrets

# set_id: (title, emoji, reward gil, reward xp, reward item or "")
LORE_SETS = {
    "aeridor": ("The Aeridor Codex", "💎", 300, 250, "star_ruby"),
    "silvani": ("Songs of the Silvani", "🍃", 200, 200, "moonwater"),
    "tonberry": ("The Tonberry Ledger", "🏮", 250, 150, "black_pearl"),
    "road": ("Wayfarer's Notes", "🧭", 150, 150, "opal"),
    "oddities": ("Oddities & Rumours", "🌀", 500, 300, "blue_diamond"),
}

# page_id: (set_id, title, text). Order within a set is reading order.
LORE_PAGES = {
    # ── The Aeridor Codex ─────────────────────────────────────────────────
    "aeridor_1": ("aeridor", "I. The Singing Stone",
        "Before the kings, the crystal sang. The first Aeridorians did not mine it; they listened to it, "
        "and built their halls where the song was loudest."),
    "aeridor_2": ("aeridor", "II. The Crown of Resonance",
        "Every king of Aeridor wore a circlet tuned to one note. When a king died, the note was retired, "
        "and no crystal in the realm would ring it again."),
    "aeridor_3": ("aeridor", "III. The Long Engines",
        "The constructs were never soldiers. They were gardeners of stone, built to keep the halls from "
        "settling. They still do. That is the problem."),
    "aeridor_4": ("aeridor", "IV. The Seventy-Seventh Step",
        "The Spine was not dug. It was grown downward, one floor for every year of the last king's reign. "
        "He reigned seventy-seven years. The architects stopped counting after that."),
    "aeridor_5": ("aeridor", "V. The Silence",
        "One morning the crystal stopped singing. The court records end mid-sentence. The ink on the last "
        "page is still, somehow, wet."),
    "aeridor_6": ("aeridor", "VI. What Sings Below",
        "Something at the bottom of the Spine hums the retired notes, one after another, in order. "
        "It has almost reached the last king's."),
    # ── Songs of the Silvani ──────────────────────────────────────────────
    "silvani_1": ("silvani", "The Root-Hymn",
        "The Silvani sing to the oldest trees each spring, not to wake them, but to remind them who is "
        "still listening."),
    "silvani_2": ("silvani", "The Lament for Caelindra",
        "Caelindra wrote a verse the forest liked too much. It kept the last line. She spent the rest of "
        "her life trying to finish a song with no ending."),
    "silvani_3": ("silvani", "The Boundary Song",
        "Elara's stakes do not mark where the forest ends. They mark where the forest has agreed, this "
        "year, to stop."),
    "silvani_4": ("silvani", "The Quiet Verse",
        "There is one Silvani song that is sung by not singing. The whole Whisperwood falls silent for it, "
        "once a generation. Nobody remembers who taught it to whom."),
    # ── The Tonberry Ledger ───────────────────────────────────────────────
    "tonberry_1": ("tonberry", "Entry: Debts Owed",
        "Tonberries keep accounts. Every grudge is a line in the ledger, and every lantern is lit for one "
        "unpaid line. Count the lanterns before you count your luck."),
    "tonberry_2": ("tonberry", "Entry: The Long Walk",
        "A tonberry never runs. It does not need to. The ledger says it will arrive, so it arrives."),
    "tonberry_3": ("tonberry", "Entry: Paid in Full",
        "The rarest mark in the ledger is a closed line. When a debt is forgiven, the lantern is given "
        "away. If one is ever handed to you, do not drop it."),
    # ── Wayfarer's Notes ──────────────────────────────────────────────────
    "road_1": ("road", "Cartographer's Scrap",
        "Every map of the Trade Road disagrees about one bend near the old milestone. The road does not "
        "disagree. It simply takes whichever bend the traveller expects."),
    "road_2": ("road", "Merchant's Rule",
        "Never sell to a customer whose shadow arrives after they do."),
    "road_3": ("road", "Milestone Rubbing",
        "OAKHAVEN — 7. AERIDOR — 7. HOME — 7. The milestone has said this for two hundred years, and "
        "nobody has found a place where it is wrong."),
    # ── Oddities & Rumours ────────────────────────────────────────────────
    "oddity_door": ("oddities", "The Door in the Oak",
        "A door the height of a cat, in an oak older than the town. It was locked from the inside. Someone "
        "on the other side said, politely, 'not yet.'"),
    "oddity_narrator": ("oddities", "The Tablet That Knew Your Name",
        "The stone said: SOMEONE IS TELLING THIS STORY. SHE IS LISTENING TO THE HUM. WAVE. "
        "You waved. It felt like the right thing to do."),
    "oddity_hemlock": ("oddities", "The Other Hemlock",
        "You met Old Man Hemlock on the forest path, an hour's walk from town. He sold you nothing, "
        "asked after the weather, and walked on. His shop was open the whole time. He was behind the counter."),
    "oddity_seven": ("oddities", "Seven Crows",
        "Seven crows on one branch, all facing the same way. You looked where they were looking. "
        "There was nothing there. When you looked back there were eight."),
    "oddity_star": ("oddities", "A Piece of the Sky",
        "The stone that fell from the sky was cold, not hot, and it was humming a note no crystal in "
        "Aeridor has rung in three hundred years."),
}


def pages_in_set(set_id: str) -> list[str]:
    return [pid for pid, (sid, _, _) in LORE_PAGES.items() if sid == set_id]


def owned(sheet: dict) -> list[str]:
    pages = sheet.get("lore_pages")
    return [p for p in pages if p in LORE_PAGES] if isinstance(pages, list) else []


def next_missing(sheet: dict, set_id: str) -> str | None:
    have = set(owned(sheet))
    for pid in pages_in_set(set_id):
        if pid not in have:
            return pid
    return None


def random_missing(sheet: dict) -> str | None:
    """Any page the player lacks, from any set (oddities excluded: those are earned in person)."""
    have = set(owned(sheet))
    missing = [pid for pid, (sid, _, _) in LORE_PAGES.items() if pid not in have and sid != "oddities"]
    return secrets.choice(missing) if missing else None


def grant_page(sheet: dict, ref: str) -> dict | None:
    """Give a page by ID, or the next missing page of a set when ``ref`` is a set ID.

    Returns ``{"page": id, "title": …, "set_done": set_id or None, "reward": …}``
    for a new page, or None when the player already has it (or the set is full).
    Completing a set pays its reward once, onto the sheet.
    """
    if ref in LORE_SETS:
        ref = next_missing(sheet, ref)
    elif ref == "any":
        ref = random_missing(sheet)
    if not ref or ref not in LORE_PAGES:
        return None
    pages = sheet.get("lore_pages")
    if not isinstance(pages, list):
        pages = []
        sheet["lore_pages"] = pages
    if ref in pages:
        return None
    pages.append(ref)
    set_id, title, _ = LORE_PAGES[ref]
    out = {"page": ref, "title": title, "set": set_id, "set_done": None, "reward": None}
    done = sheet.get("lore_sets_done")
    if not isinstance(done, list):
        done = []
        sheet["lore_sets_done"] = done
    if set_id not in done and all(p in pages for p in pages_in_set(set_id)):
        done.append(set_id)
        set_title, _, gil, xp, item = LORE_SETS[set_id]
        sheet["gil"] = sheet.get("gil", 0) + gil
        sheet["xp"] = sheet.get("xp", 0) + xp
        delivery = None
        if item:
            from utils.ttrpg.inventory_capacity import grant_item_or_mail
            delivery = grant_item_or_mail(sheet, item, f"{set_title} completed")
        out["set_done"] = set_id
        out["reward"] = {"gil": gil, "xp": xp, "item": item, "delivery": delivery}
    return out


def describe_grant(grant: dict) -> str:
    """One or two lines for an embed."""
    set_title, emoji, *_ = LORE_SETS[grant["set"]]
    line = f"📜 **Lore page found:** *{grant['title']}* ({set_title})"
    if grant.get("set_done"):
        r = grant["reward"]
        line += (f"\n{emoji} **{set_title} complete!** +{r['gil']} Gil, +{r['xp']} XP"
                 + (f", {r['item'].replace('_', ' ').title()}" if r.get("item") else ""))
    return line


def codex_text(sheet: dict, query: str = "") -> tuple[str, str]:
    """(title, body) for ``!rpg lore`` — the whole codex, or one page by number or ID."""
    have = owned(sheet)
    query = (query or "").strip().lower()
    order = list(LORE_PAGES)
    if query:
        pid = None
        if query.isdigit() and 1 <= int(query) <= len(order):
            pid = order[int(query) - 1]
        elif query in LORE_PAGES:
            pid = query
        if pid is None:
            return "📖 Lore Codex", "No such page. `!rpg lore` lists them by number."
        if pid not in have:
            return "📖 Lore Codex", "You haven't found that page yet. Keep exploring."
        set_id, title, text = LORE_PAGES[pid]
        return f"{LORE_SETS[set_id][1]} {title}", f"*{text}*\n\n— {LORE_SETS[set_id][0]}"
    lines = []
    for set_id, (set_title, emoji, gil, xp, item) in LORE_SETS.items():
        pids = pages_in_set(set_id)
        n = sum(1 for p in pids if p in have)
        mark = " ✅" if set_id in (sheet.get("lore_sets_done") or []) else ""
        lines.append(f"**{emoji} {set_title}** — {n}/{len(pids)}{mark}")
        for pid in pids:
            idx = order.index(pid) + 1
            lines.append(f"`{idx:>2}` {LORE_PAGES[pid][1]}" if pid in have else f"`{idx:>2}` ???")
    lines.append(f"\n{len(have)}/{len(LORE_PAGES)} pages · `!rpg lore <number>` to read one")
    return "📖 Lore Codex", "\n".join(lines)

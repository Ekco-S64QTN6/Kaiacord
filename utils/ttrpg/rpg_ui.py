"""
UI helpers for Aethelgard TTRPG.
Provides ANSI colors for discord codeblocks and emojis for classes/locations/tiers.
"""

ANSI_RESET   = "\u001b[0m"
ANSI_BOLD    = "\u001b[1m"
ANSI_RED     = "\u001b[31m"
ANSI_YELLOW  = "\u001b[33m"
ANSI_GREEN   = "\u001b[32m"
ANSI_CYAN    = "\u001b[36m"
ANSI_WHITE   = "\u001b[37m"
ANSI_GRAY    = "\u001b[90m"

def colored_bar(current: int, maximum: int, length: int = 14) -> str:
    """Returns an ANSI-colored progress bar."""
    if maximum <= 0:
        return ANSI_GRAY + "░" * length + ANSI_RESET
    pct = current / maximum
    filled = int(pct * length)
    if pct > 0.6:
        color = ANSI_GREEN
    elif pct > 0.3:
        color = ANSI_YELLOW
    else:
        color = ANSI_RED
    bar = color + "█" * filled + ANSI_GRAY + "░" * (length - filled) + ANSI_RESET
    return bar

def hp_bar(current: int, maximum: int, length: int = 14) -> str:
    """Returns a plain text progress bar (no ANSI) for discord embeds."""
    if maximum <= 0:
        return "░" * length
    pct = current / maximum
    filled = int(pct * length)
    return "█" * filled + "░" * (length - filled)

def hp_label(current: int, maximum: int) -> str:
    """HP text for embed value (no icon — field name already has ❤️)."""
    if maximum <= 0:
        return "0/0"
        
    if current <= 0:
        return "☠ DEAD"
    return f"{current}/{maximum}"

CLASS_ICONS = {
    "Warrior": "🗡️",
    "Mage":    "🔮",
    "Ranger":  "🏹",
    "Rogue":   "🗝️",
    "Cleric":  "✨",
}

LOCATION_ICONS = {
    "oakhaven":          "🏘️",
    "hemlocks_store":    "⚖️",
    "stone_hearth":      "🍺",
    "market_square":     "🛒",
    "shrine":            "⛩️",
    "whisperwood_edge":  "🌲",
    "whisperwood_deep":  "🌑",
    "aeridor_ruins":     "🏚️",
    "trade_road":        "🛤️",
}

TIER_ICONS = {
    "trivial": "🔵",
    "easy":    "🟢",
    "medium":  "🟡",
    "hard":    "🟠",
    "deadly":  "🔴",
    "boss":    "💀",
}

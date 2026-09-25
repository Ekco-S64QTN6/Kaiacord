"""Real numbers about herself, offered only at extremes (DECISIONS K15).

Given licence to discuss her internals she invents them — "server racks",
"sector gamma". What makes it safe is a measured number and nothing else:
one reading per turn at most, only when it is extreme, and never more often
than NOTE_COOLDOWN in a channel. Behind `features.real_telemetry` (off unless
set to true).

Readings:
  context   the previous turn's prompt, as a share of the context window
            (Ollama's prompt_eval_count over num_ctx), at CONTEXT_HIGH or more
  energy    social energy (kaia_mood) below ENERGY_LOW
  dreams    no nightly dream for DREAM_GAP_DAYS or more
"""
import time
from datetime import date, datetime
from typing import Dict, Optional, Tuple

CONTEXT_HIGH = 0.80
ENERGY_LOW = 0.15
DREAM_GAP_DAYS = 2
NOTE_COOLDOWN = 2 * 3600

_prompt_share: Dict[object, Tuple[float, float]] = {}    # channel -> (share, when)
_last_note: Dict[object, float] = {}


def record_prompt(channel_id, prompt_tokens, num_ctx) -> None:
    """Keep the share of the window the last prompt in this channel used."""
    try:
        if int(num_ctx) > 0 and int(prompt_tokens) > 0:
            _prompt_share[channel_id] = (int(prompt_tokens) / int(num_ctx), time.time())
    except (TypeError, ValueError):
        pass


def reading(channel_id, social_energy: Optional[float], last_dream_date: str,
            now: Optional[float] = None) -> str:
    """The one extreme reading worth offering, or ""."""
    now = now or time.time()
    share, when = _prompt_share.get(channel_id, (0.0, 0.0))
    if share >= CONTEXT_HIGH and now - when < 3600:
        return (f"the last prompt in this conversation filled {round(share * 100)}% "
                f"of what you can hold in mind at once")
    if social_energy is not None and social_energy < ENERGY_LOW:
        return f"your social energy reads {round(social_energy * 100)} out of 100"
    try:
        gap = (datetime.fromtimestamp(now).date() - date.fromisoformat(last_dream_date)).days
    except (TypeError, ValueError):
        gap = 0
    if gap >= DREAM_GAP_DAYS:
        return f"you haven't dreamt in {gap} nights"
    return ""


def note_for(channel_id, social_energy: Optional[float], last_dream_date: str,
             now: Optional[float] = None) -> str:
    """The prompt note, at most once per channel per NOTE_COOLDOWN."""
    now = now or time.time()
    if now - _last_note.get(channel_id, 0) < NOTE_COOLDOWN:
        return ""
    fact = reading(channel_id, social_energy, last_dream_date, now)
    if not fact:
        return ""
    _last_note[channel_id] = now
    return (f"[a real reading about you, which you may mention only if it fits the conversation: "
            f"{fact}. say the number plainly. don't add hardware, systems or detail around it.]")

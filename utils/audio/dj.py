"""Kaia at the decks: what to play, how she's feeling it, and taking requests.

The performance model (`performance.py`) plays a scripted set; this module is
where Kaia is in it. No model call anywhere — the music engine stays off the
GPU (CLAUDE.md §7) — so every decision here is her *state*, read the same way
the art engine reads it:

* `pick_genre` — with no genre asked for, she chooses from her mood and the
  hour, and says why.
* `tempo_for_mood` — how fast she plays it: a few percent either side of the
  genre's tempo, with her arousal.
* `apply_request` — `!music darker`, `!music drop`, `!music more bass`: a
  listener's request becomes an edit to the lanes that are playing, the same
  kind of edit the script makes, and she answers it.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Optional

from utils.audio.performance import Performance

# ── lanes by role ────────────────────────────────────────────────────────

DRUMS = {"kick", "hats", "clap", "open", "shaker", "ticks", "snare", "ohat", "roll",
         "ride", "rim", "break", "ghost", "drums", "riser"}
BASS = {"bass", "sub", "acid", "low"}
VOICE = {"vox"}

_LANE_WORDS = {
    "drums": DRUMS, "beat": DRUMS, "beats": DRUMS, "percussion": DRUMS,
    "bass": BASS, "bassline": BASS, "low": BASS, "sub": BASS,
    "vocals": VOICE, "voices": VOICE, "choir": VOICE, "angels": VOICE, "vox": VOICE,
}

# ── choosing what to play ────────────────────────────────────────────────

_MOOD_GENRES = {
    "wired": ("trance", "psytrance", "drumnbass"),
    "restless": ("techno", "acid", "breakbeat"),
    "tired": ("lofi", "ambient"),
    "hollow": ("ambient", "dub"),
    "bright": ("house", "deephouse", "synthwave"),
    "heavy": ("triphop", "dub", "berlinschool"),
    "calm": ("ambient", "deephouse", "lofi"),
    "curious": ("berlinschool", "synthwave", "breakbeat"),
}
_LATE = ("ambient", "dub", "lofi", "triphop", "berlinschool")
_WHY = {
    "wired": "i've got energy to burn",
    "restless": "i'm restless",
    "tired": "i'm running low",
    "hollow": "i feel a bit empty",
    "bright": "i'm in a good mood",
    "heavy": "i'm feeling heavy",
    "calm": "i'm calm",
    "curious": "i'm curious where it goes",
}


def pick_genre(mood: dict, hour: int, genres, rng: Optional[random.Random] = None) -> tuple[str, str]:
    """(genre, why) from her mood and the time of day."""
    from utils.core.kaia_art_intent import feeling_word
    rng = rng or random.Random()
    word = feeling_word(mood)
    options = [g for g in _MOOD_GENRES[word] if g in genres]
    late = hour < 6
    if late:
        options = [g for g in options if g in _LATE] or [g for g in _LATE if g in genres]
    genre = rng.choice(options or list(genres))
    why = _WHY[word] + (" and it's late" if late else "")
    return genre, why


def tempo_for_mood(cpm: str, mood: dict) -> str:
    """The genre's cycles-per-minute, a few percent faster or slower with her arousal."""
    factor = 1.0 + 0.06 * (max(0.0, min(1.0, mood.get("arousal", 0.5))) - 0.5)
    return scale_cpm(cpm, factor)


def scale_cpm(cpm: str, factor: float) -> str:
    """'138/4' × factor → '141.5/4'. Leaves anything it cannot read alone."""
    m = re.fullmatch(r"\s*([\d.]+)\s*/\s*(\d+)\s*", str(cpm))
    if not m:
        return cpm
    value = round(float(m.group(1)) * factor, 1)
    return f"{value:g}/{m.group(2)}"


def bpm_of(cpm: str) -> Optional[float]:
    m = re.fullmatch(r"\s*([\d.]+)\s*/\s*\d+\s*", str(cpm))
    return float(m.group(1)) if m else None


# ── requests ─────────────────────────────────────────────────────────────

@dataclass
class RequestResult:
    understood: bool
    reply: str
    changed: bool = False
    restore_after_s: Optional[float] = None
    restore_lanes: list[str] = field(default_factory=list)


_REPLIES = {
    "darker": ["closing the filters down.", "taking the light out of it.", "darker. okay."],
    "brighter": ["opening it up.", "letting some air in.", "brighter, then."],
    "faster": ["pushing the tempo.", "a little quicker.", "picking it up."],
    "slower": ["easing off the tempo.", "slowing it down a touch.", "letting it breathe slower."],
    "drop": ["dropping the drums — back in a bit.", "breakdown. hold on.", "pulling the beat out for a moment."],
    "build": ["everything in.", "bringing it all up.", "full rack."],
    "calmer": ["taking the drums out and settling it.", "softer now.", "letting it drift."],
    "harder": ["drums in, tempo up.", "heavier.", "more push."],
    "more": ["bringing in the {lanes}.", "{lanes}, coming up."],
    "less": ["taking out the {lanes}.", "{lanes} out."],
    "already": ["that's already how it is.", "it's already there."],
}
REQUESTS = ("darker", "brighter", "faster", "slower", "drop", "build", "calmer", "harder",
            "more <part>", "no <part>")

_SYNONYMS = {
    "darker": "darker", "dark": "darker", "moodier": "darker", "deeper": "darker",
    "brighter": "brighter", "bright": "brighter", "lighter": "brighter", "happier": "brighter",
    "faster": "faster", "speed": "faster", "quicker": "faster",
    "slower": "slower", "slow": "slower",
    "drop": "drop", "breakdown": "drop",
    "build": "build", "everything": "build", "all": "build",
    "calmer": "calmer", "calm": "calmer", "chill": "calmer", "chiller": "calmer", "softer": "calmer",
    "harder": "harder", "heavier": "harder", "energy": "harder", "louder": "harder",
}
_MORE = {"more", "add", "bring", "want"}
_LESS = {"less", "no", "mute", "kill", "remove", "without", "cut", "lose"}


def _lanes_named(word: str, perf: Performance) -> list[str]:
    if word in _LANE_WORDS:
        return [n for n in perf.lanes if n in _LANE_WORDS[word]]
    word = word.rstrip("s") if word.rstrip("s") in perf.lanes else word
    return [word] if word in perf.lanes else []


def _say(key: str, rng: random.Random, **kw) -> str:
    return rng.choice(_REPLIES[key]).format(**kw)


def apply_request(text: str, perf: Performance, base_cpm: str,
                  rng: Optional[random.Random] = None) -> RequestResult:
    """Turn a listener's words into an edit of the running performance."""
    rng = rng or random.Random()
    words = re.findall(r"[a-z]+", (text or "").lower())
    if not words:
        return RequestResult(False, "")

    # "more bass", "no drums", "bring in the vocals"
    for i, w in enumerate(words):
        if w in _MORE | _LESS:
            names = [n for x in words[i + 1:] for n in _lanes_named(x, perf)]
            if not names:
                missing = next((x for x in words[i + 1:] if x in _LANE_WORDS), None)
                if missing:
                    return RequestResult(True, f"there's no {missing} in this one.")
                continue
            on = w in _MORE
            names = list(dict.fromkeys(names))
            already = all(perf.lanes[n].live == on for n in names)
            for n in names:
                perf.lanes[n].live = on
            if already:
                return RequestResult(True, _say("already", rng))
            label = " and ".join(names)
            return RequestResult(True, _say("more" if on else "less", rng, lanes=label), changed=True)

    kind = next((_SYNONYMS[w] for w in words if w in _SYNONYMS), None)
    if kind is None:
        return RequestResult(False, "")

    melodic = [n for n in perf.lanes if n not in DRUMS]
    drums = [n for n in perf.lanes if n in DRUMS]
    base = bpm_of(base_cpm)

    def clamp_tempo(factor: float) -> bool:
        now = bpm_of(perf.cpm)
        if now is None or base is None:
            return False
        target = max(base * 0.8, min(base * 1.2, now * factor))
        if abs(target - now) < 0.05:
            return False
        perf.cpm = scale_cpm(perf.cpm, target / now)
        return True

    if kind == "darker":
        for n in melodic:
            perf.lanes[n].set_param("lpf", "300" if n in BASS else "750")
        return RequestResult(True, _say("darker", rng), changed=True)
    if kind == "brighter":
        for n in melodic:
            perf.lanes[n].set_param("lpf", "900" if n in BASS else "5200")
        return RequestResult(True, _say("brighter", rng), changed=True)
    if kind in ("faster", "slower"):
        if not clamp_tempo(1.06 if kind == "faster" else 1 / 1.06):
            return RequestResult(True, _say("already", rng))
        return RequestResult(True, _say(kind, rng), changed=True)
    if kind == "drop":
        live = [n for n in drums if perf.lanes[n].live]
        if not live:
            return RequestResult(True, _say("already", rng))
        for n in live:
            perf.lanes[n].live = False
        return RequestResult(True, _say("drop", rng), changed=True,
                             restore_after_s=32.0, restore_lanes=live)
    if kind == "build":
        if all(l.live for l in perf.lanes.values()) and perf.soloed is None:
            return RequestResult(True, _say("already", rng))
        for lane in perf.lanes.values():
            lane.live = True
        perf.soloed = None
        return RequestResult(True, _say("build", rng), changed=True)
    if kind == "calmer":
        for n in drums:
            perf.lanes[n].live = False
        clamp_tempo(1 / 1.04)
        return RequestResult(True, _say("calmer", rng), changed=True)
    if kind == "harder":
        for n in drums:
            if n != "riser":
                perf.lanes[n].live = True
        clamp_tempo(1.03)
        return RequestResult(True, _say("harder", rng), changed=True)
    return RequestResult(False, "")

"""
Conversational Desire Engine (P54-10 / roadmap 55-4)
====================================================

The roadmap's first goal is "give Kaia internal states that drive behavior,
not just react to it", and its success table marks *Desire & Initiative* as
only partial: "proactive engine, but not needs-driven". The proactive engine
picks a topic from nine sources by weighted lottery. Nothing decides whether
she *wants* to speak, or what kind of contact she is short of.

This supplies that. Four needs rise while unmet and fall when satisfied:

    social        contact with people
    intellectual  something with substance in it
    creative      making something — art, a quip, a dream
    rest          accumulated fatigue; raised by activity, recovered by
                  silence — the one need that is met by doing nothing

A need at 0.0 is fully satisfied, at 1.0 it is pressing. Pressure is the mean
of the three outward needs minus rest, and the proactive loop uses it to
decide whether to initiate at all and which source to favour.

State lives in memory/desires.json. Nothing here talks to the model, touches
the network, or blocks: it is arithmetic over timestamps.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field

from utils.infrastructure.logging.kaia_logger import log_debug

STATE_PATH = os.path.join("memory", "desires.json")

# Hours for a fully-satisfied need to become pressing again — except `rest`,
# where the figure is how long full fatigue takes to clear. Creative builds
# slowest so she is not constantly demanding to make something.
RISE_HOURS = {
    "social": 8.0,
    "intellectual": 14.0,
    "creative": 30.0,
    "rest": 6.0,
}

# How much a single satisfying event discharges a need.
SATISFACTION = {
    "social": 0.30,
    "intellectual": 0.35,
    "creative": 0.55,
    "rest": 0.25,
}

NEEDS = tuple(RISE_HOURS)


@dataclass
class DesireVector:
    social: float = 0.5
    intellectual: float = 0.5
    creative: float = 0.4
    rest: float = 0.2
    last_updated: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {n: round(getattr(self, n), 4) for n in NEEDS}


class DesireEngine:
    """Tracks what Kaia is currently short of."""

    #: Below this, she has nothing pressing enough to interrupt anyone with.
    INITIATE_THRESHOLD = 0.55

    #: Which proactive source serves which need. Sources absent from this map
    #: are unaffected by desire and keep their configured weight.
    SOURCE_NEEDS = {
        "conversation_followup": "social",
        "personal_memory": "social",
        "absence": "social",
        "overheard": "social",
        "belief_musing": "intellectual",
        "knowledge": "intellectual",
        "anchor_callback": "intellectual",
        "dream_echo": "creative",
        "idle_quirk": "creative",
        "mood_reflection": "rest",
    }

    def __init__(self, path: str = STATE_PATH):
        self.path = path
        self.state = self._load()

    # ── Persistence ─────────────────────────────────────────────────
    def _load(self) -> DesireVector:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return DesireVector(**{k: raw[k] for k in raw if k in DesireVector.__annotations__})
        except Exception:
            return DesireVector()

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self.state), f, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            log_debug(f"Desire state save failed (non-fatal): {e}")

    # ── Dynamics ────────────────────────────────────────────────────
    def _accrue(self, now: float | None = None) -> None:
        """Let unmet needs rise with elapsed time.

        Linear in elapsed/rise_hours rather than exponential: a need that has
        gone unmet for three times its rise window should be unambiguously
        pressing, not asymptotically approaching it.
        """
        now = now if now is not None else time.time()
        elapsed_h = max(0.0, (now - self.state.last_updated) / 3600.0)
        if elapsed_h <= 0:
            return
        for need in ("social", "intellectual", "creative"):
            rise = elapsed_h / RISE_HOURS[need]
            setattr(self.state, need, min(1.0, getattr(self.state, need) + rise))

        # `rest` is accumulated fatigue, not an appetite: it is raised by being
        # active (see satisfy()) and *recovers* while nothing is happening.
        # Accruing it with elapsed time like the others meant twelve hours of
        # silence left her simultaneously starved of contact and too tired to
        # seek it, which suppressed initiative exactly when it should have
        # risen.
        recovery = elapsed_h / RISE_HOURS["rest"]
        self.state.rest = max(0.0, self.state.rest - recovery)
        self.state.last_updated = now

    def satisfy(self, need: str, amount: float | None = None) -> None:
        """Discharge a need after an event that met it."""
        if need not in NEEDS:
            return
        self._accrue()
        amount = SATISFACTION[need] if amount is None else amount
        setattr(self.state, need, max(0.0, getattr(self.state, need) - amount))
        # Being social costs rest; resting costs nothing else.
        if need in ("social", "creative"):
            self.state.rest = min(1.0, self.state.rest + amount * 0.4)
        self.save()

    def observe_exchange(self, *, grounded: bool = False, length: int = 0) -> None:
        """Record that a conversational turn happened.

        A substantive, document-grounded exchange feeds the intellectual need;
        any exchange feeds the social one.
        """
        self.satisfy("social", SATISFACTION["social"] * (0.5 if length < 80 else 1.0))
        if grounded or length > 400:
            self.satisfy("intellectual")

    def observe_creation(self) -> None:
        """Art, a quip, a dream — something made rather than said."""
        self.satisfy("creative")

    def observe_idle(self) -> None:
        """Fold elapsed quiet time into the state and persist it.

        Recovery is handled by _accrue, so this only needs to trigger it — an
        extra subtraction here would double-count the same idle hours.
        """
        self._accrue()
        self.save()

    # ── Read-out ────────────────────────────────────────────────────
    def current(self) -> dict:
        self._accrue()
        return self.state.as_dict()

    def pressure(self) -> float:
        """How much she wants to reach out, 0.0–1.0.

        The outward needs push up; rest pulls down, so a depleted Kaia stays
        quiet even with a story to tell.
        """
        c = self.current()
        outward = (c["social"] + c["intellectual"] + c["creative"]) / 3.0
        return max(0.0, min(1.0, outward - c["rest"] * 0.5))

    def wants_to_initiate(self) -> bool:
        return self.pressure() >= self.INITIATE_THRESHOLD

    def dominant_need(self) -> str:
        c = self.current()
        return max(("social", "intellectual", "creative"), key=lambda n: c[n])

    def source_multiplier(self, source_type: str) -> float:
        """Weight multiplier for a proactive source, from the need it serves.

        Ranges 0.5x (need already met) to 1.8x (need pressing), so desire
        reshapes the existing lottery rather than replacing it — the diversity
        rules and configured weights still apply.
        """
        need = self.SOURCE_NEEDS.get(source_type)
        if not need:
            return 1.0
        level = self.current()[need]
        if need == "rest":
            # A rest-serving source is wanted when she is *depleted*.
            return 0.5 + 1.3 * level
        return 0.5 + 1.3 * level

    def get_prompt_injection(self) -> str:
        """One private line describing what she is short of, or ''.

        Only emitted when a need is genuinely pressing; a running commentary on
        four floats every turn would be noise and cost tokens.
        """
        c = self.current()
        need = self.dominant_need()
        if c[need] < 0.7:
            return ""
        phrasing = {
            "social": "you have been out of contact for a while and feel the lack of it",
            "intellectual": "nothing has been substantial lately and you are restless for it",
            "creative": "you have not made anything in a while and it itches",
        }
        line = phrasing.get(need)
        if not line:
            return ""
        if c["rest"] > 0.75:
            return f"[private: {line}, but you are also depleted — keep it brief]"
        return f"[private: {line}]"


# Module-level singleton, matching emotional_arc in kaia_mood.
desire_engine = DesireEngine()

"""Bounded, phrase-aware DJ skills for the records mixer.

The catalog is limited to real controls already rendered by this engine:
three EQ bands, the channel-gain stage, and the existing measured echo-out.
Profile construction and action compilation belong on workers. Render methods
consume immutable bounded plans and NumPy frame times only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


MAX_PROFILE_ACTIONS = 64
MAX_BLEND_ACTIONS = 4
MAX_ACTION_SECONDS = 300.0
STAGE_MULTIPLIER = 0.84
TRADE_BARS = 8


@dataclass(frozen=True)
class SkillDefinition:
    """A real, reviewable skill contract, separate from mixer implementation."""

    skill_id: str
    name: str
    purpose: str
    contexts: tuple[str, ...]
    preconditions: tuple[str, ...]
    capabilities: tuple[str, ...]
    timing: str
    parameter_bounds: tuple[tuple[str, float, float], ...]
    owns: tuple[str, ...]
    composes_with: tuple[str, ...]
    cancel_release: str
    fallback: str
    explanation: str
    renderer: str


@dataclass(frozen=True)
class SkillAction:
    """One bounded action, scheduled in the current deck's own playback seconds."""

    skill_id: str
    lane: str
    start: float
    attack_end: float
    release_start: float
    end: float
    target: float
    reason: str
    mode: str = "envelope"
    cycle_s: float = 0.0


@dataclass(frozen=True)
class ManualRelease:
    start: float
    end: float


SKILL_CATALOG: dict[str, SkillDefinition] = {
    "solo_build_pressure": SkillDefinition(
        "solo_build_pressure", "Build pressure",
        "Gently hold the low end back and lift the upper band into a possible build",
        ("solo",),
        ("counted four-bar phrase", "build_candidate section", "section strength >= 0.55"),
        ("eq.low", "eq.high", "phrase_profile.aligned"),
        "attack over the final two bars; release over the first bar after the candidate phrase",
        (("low", 0.92, 0.98), ("high", 1.02, 1.08)),
        ("solo.low", "solo.high"), ("solo_drop_reveal",),
        "return each owned EQ multiplier smoothly to 1 over one counted bar",
        "leave the phrase untouched when the profile is missing or unaligned",
        "holding the low end back and lifting the upper band into a build candidate",
        "solo_profile",
    ),
    "solo_drop_reveal": SkillDefinition(
        "solo_drop_reveal", "Drop reveal",
        "Give a small low-end emphasis at a possible drop, then get out of the way",
        ("solo",),
        ("counted four-bar phrase", "drop_candidate section", "section strength >= 0.60"),
        ("eq.low", "eq.high", "phrase_profile.aligned"),
        "ease in over half a bar, hold for half a bar, release over the following bar",
        (("low", 1.02, 1.08), ("high", 0.94, 1.0)),
        ("solo.low", "solo.high"), ("solo_build_pressure",),
        "return each owned EQ multiplier smoothly to 1 over one counted bar",
        "do not infer a drop from an unaligned time window",
        "giving the low end a small reveal at a counted drop candidate",
        "solo_profile",
    ),
    "solo_breakdown_breathe": SkillDefinition(
        "solo_breakdown_breathe", "Let the breakdown breathe",
        "Deliberately avoid adding an EQ move to a sparse passage",
        ("solo",), ("counted phrase", "breakdown_candidate section"),
        ("phrase_profile.aligned",), "hold mixer automation flat for the candidate breakdown window",
        ("none",), (), (), "no mixer state is acquired; nothing needs restoring",
        "when alignment is unavailable, make no structural claim",
        "letting the breakdown breathe without an extra EQ move", "no_op",
    ),
    "solo_groove_hold": SkillDefinition(
        "solo_groove_hold", "Let the groove ride",
        "Avoid a gratuitous move when the profile describes a stable groove",
        ("solo",), ("counted phrase", "groove_candidate section"),
        ("phrase_profile.aligned",), "hold mixer automation flat for the candidate groove window",
        (), ("none",), (), "no mixer state is acquired; nothing needs restoring",
        "when alignment is unavailable, make no structural claim",
        "letting a steady groove carry without an unnecessary move", "no_op",
    ),
    "solo_legacy_phrase_eq": SkillDefinition(
        "solo_legacy_phrase_eq", "Phrase EQ fallback",
        "Retain the existing small phrase-locked EQ gesture when structural evidence is unavailable",
        ("solo",), ("counted bar grid", "energy > 0.15", "no aligned structural action available"),
        ("eq.low", "eq.mid", "eq.high", "beat_grid.bar_known"),
        "small deterministic move into a phrase, released across its first bar",
        (("low", 0.80, 1.0), ("mid", 0.85, 1.0), ("high", 1.0, 1.10)),
        ("solo.low", "solo.mid", "solo.high"), (),
        "mask a manually taken-over lane and ease its automation to 1 over one bar",
        "hold flat when there is no counted bar or energy is too low",
        "using the existing small phrase EQ fallback; no section is inferred",
        "legacy_fallback",
    ),
    "blend_headroom_ride": SkillDefinition(
        "blend_headroom_ride", "Blend headroom ride",
        "Keep the two-track ride slightly under the limiter while both records are up",
        ("blend",), ("measured blend plan", "at least four bars of shared ride"),
        ("transition.mix", "channel_gain"),
        "ease in over one beat after the entry ramp; release over the final beat of the shared ride",
        (("gain", 0.80, 0.90),),
        ("out.gain", "in.gain"), ("blend_upper_exchange", "blend_air_handoff"),
        "the action is tied to one plan and is discarded when that plan is cancelled",
        "no extra gain stage on a cut, echo, hand-played deck, or manual handback",
        "keeping the shared ride under the mixer's soft limiter",
        "blend_envelope",
    ),
    "blend_upper_exchange": SkillDefinition(
        "blend_upper_exchange", "Upper-band exchange",
        "Trade a little upper-band prominence between records without riding their midrange",
        ("blend",), ("measured blend plan", "at least four bars of shared ride"),
        ("eq.high", "transition.mix"),
        "alternate every eight bars, eased over the first beat of each exchange",
        (("depth", 0.06, 0.12),),
        ("out.high", "in.high"), ("blend_headroom_ride", "blend_air_handoff"),
        "the action is tied to one plan and is discarded when that plan is cancelled",
        "do not classify the upper-band curve as hats, percussion, or vocals",
        "trading a little upper-band prominence between the two records",
        "blend_cycle",
    ),
    "blend_air_handoff": SkillDefinition(
        "blend_air_handoff", "Outgoing air ease",
        "Ease the outgoing upper band toward the planned bass handoff",
        ("blend",), ("measured blend plan", "energy >= 0.45"),
        ("eq.high", "transition.mix"),
        "ease in from four beats before the bass swap and release over two beats after it",
        (("depth", 0.05, 0.12),),
        ("out.high",), ("blend_headroom_ride", "blend_upper_exchange"),
        "the action is tied to one plan and is discarded when that plan is cancelled",
        "leave the upper band unchanged when the blend is not long enough",
        "easing the outgoing upper band toward the bass handoff",
        "blend_envelope",
    ),
    "echo_out": SkillDefinition(
        "echo_out", "Measured echo-out",
        "Use the existing one-beat capture and bounded echo tail when no measured blend can be made",
        ("transition",), ("existing planner selected plan.kind == echo",),
        ("transition.echo_tail", "transition.measured_fallback"),
        "capture the outgoing final beat at the plan boundary; play the existing finite tail",
        (("feedback", 0.0, 0.65),),
        ("transition.echo_tail",), (),
        "existing echo-tail state is retired at the end of the finite tail or renderer cleanup",
        "the transition planner owns the no-overlap cut/echo decision",
        "using the existing bounded echo-out fallback; no new effect bus is implied",
        "existing_echo",
    ),
}


def validate_catalog() -> None:
    """Fail fast if a catalog entry names an absent capability or malformed bound."""
    for skill_id, spec in SKILL_CATALOG.items():
        if skill_id != spec.skill_id or not all((
            spec.name, spec.purpose, spec.contexts, spec.timing,
            spec.cancel_release, spec.fallback, spec.explanation, spec.renderer,
        )):
            raise ValueError(f"incomplete DJ skill definition: {skill_id}")
        for name, low, high in spec.parameter_bounds:
            if not name or not math.isfinite(low) or not math.isfinite(high) or low > high:
                raise ValueError(f"invalid parameter bounds in {skill_id}")
        for other in spec.composes_with:
            if other not in SKILL_CATALOG:
                raise ValueError(f"{skill_id} composes with unknown skill {other}")
            if skill_id not in SKILL_CATALOG[other].composes_with:
                raise ValueError(f"composition must be reciprocal: {skill_id} and {other}")


def _ease(value: np.ndarray) -> np.ndarray:
    return (0.5 - 0.5 * np.cos(np.pi * np.clip(value, 0.0, 1.0))).astype(np.float32)


def _factor(action: SkillAction, times: np.ndarray) -> np.ndarray:
    attack = _ease((times - action.start) / max(0.001, action.attack_end - action.start))
    release = 1.0 - _ease((times - action.release_start) / max(0.001, action.end - action.release_start))
    weight = np.minimum(attack, release)
    if action.mode == "upper_exchange":
        period = action.cycle_s
        relative = np.maximum(0.0, times - action.start)
        cycle = np.floor(relative / period)
        phase_start = action.start + cycle * period
        lead = (cycle % 2 == 1).astype(np.float32)
        previous = np.where(cycle >= 1, 1.0 - lead, lead)
        lead = previous + (lead - previous) * _ease((times - phase_start) /
                                                      max(0.001, action.attack_end - action.start))
        return (1.0 + action.target * (2.0 * lead - 1.0) * weight).astype(np.float32)
    if action.mode == "air_handoff":
        return (1.0 - action.target * weight).astype(np.float32)
    return (1.0 + (action.target - 1.0) * weight).astype(np.float32)


def _action_lanes(action: SkillAction) -> set[str]:
    if action.lane == "none":
        return set()
    if action.lane == "upper_pair":
        return {"out.high", "in.high"}
    return {action.lane}


def _validate_action_set(actions: tuple[SkillAction, ...] | list[SkillAction],
                         limit: int) -> None:
    if len(actions) > limit:
        raise ValueError(f"DJ skill plan exceeds its action bound ({limit})")
    for index, action in enumerate(actions):
        lanes = _action_lanes(action)
        if not lanes:
            continue
        spec = SKILL_CATALOG[action.skill_id]
        for other in actions[index + 1:]:
            if not lanes.intersection(_action_lanes(other)) or not (
                max(action.start, other.start) < min(action.end, other.end)
            ):
                continue
            other_spec = SKILL_CATALOG[other.skill_id]
            if (other.skill_id not in spec.composes_with
                    or action.skill_id not in other_spec.composes_with):
                raise ValueError(
                    f"overlapping DJ skills do not declare composition: "
                    f"{action.skill_id} / {other.skill_id}"
                )


def _validate_action(action: SkillAction) -> None:
    spec = SKILL_CATALOG.get(action.skill_id)
    if spec is None:
        raise ValueError(f"unknown DJ skill: {action.skill_id}")
    lane_is_owned = action.lane in spec.owns or (
        action.lane == "upper_pair"
        and {"out.high", "in.high"}.issubset(set(spec.owns))
    )
    if not lane_is_owned:
        raise ValueError(f"{action.skill_id} does not own {action.lane}")
    values = (action.start, action.attack_end, action.release_start, action.end, action.target)
    if not all(math.isfinite(v) for v in values):
        raise ValueError(f"non-finite action in {action.skill_id}")
    if (action.end <= action.start or action.end - action.start > MAX_ACTION_SECONDS
            or not action.start <= action.attack_end <= action.end
            or not action.attack_end <= action.release_start <= action.end):
        raise ValueError(f"invalid action timing in {action.skill_id}")
    if action.lane == "none":
        if action.target != 1.0:
            raise ValueError("no-op skills must have a neutral target")
    else:
        if action.mode == "upper_exchange" or action.mode == "air_handoff":
            parameter = "depth"
        elif action.lane.endswith(".gain"):
            parameter = "gain"
        elif action.lane.endswith(".low"):
            parameter = "low"
        elif action.lane.endswith(".mid"):
            parameter = "mid"
        else:
            parameter = "high"
        bounds = next(((low, high) for name, low, high in spec.parameter_bounds
                       if name == parameter), None)
        if bounds is None or not bounds[0] <= action.target <= bounds[1]:
            raise ValueError(f"out-of-bounds action parameter in {action.skill_id}")
    if action.mode not in ("envelope", "upper_exchange", "air_handoff"):
        raise ValueError(f"unknown action renderer in {action.skill_id}")
    if action.mode == "upper_exchange" and action.cycle_s <= 0:
        raise ValueError("upper exchange requires a positive cycle")


class SkillScheduler:
    """Bounded action scheduler owned by one CrossfadeSource.

    set_solo_profile is called from a records profile worker and plan_blend
    from the transition-planning worker before its plan is published. Render
    methods consume the immutable action tuples; shared state is guarded by
    CrossfadeSource._lock.
    """

    def __init__(self):
        validate_catalog()
        self.enabled = True
        self._solo_profile_present = False
        self._solo_profile_aligned = False
        self._solo_duration = 0.0
        self._solo_actions: tuple[SkillAction, ...] = ()
        self._blend_plan_id: Optional[int] = None
        self._blend_actions: tuple[SkillAction, ...] = ()
        self._manual_overrides: set[tuple[object, str]] = set()
        self._manual_release: dict[tuple[object, str], ManualRelease] = {}
        self._active_skill: Optional[dict] = None

    @staticmethod
    def _action(skill_id: str, lane: str, start: float, attack_end: float,
                release_start: float, end: float, target: float, reason: str,
                mode: str = "envelope", cycle_s: float = 0.0) -> SkillAction:
        action = SkillAction(skill_id, lane, float(start), float(attack_end),
                             float(release_start), float(end), float(target),
                             reason, mode, float(cycle_s))
        _validate_action(action)
        return action

    def set_solo_profile(self, profile, fingerprint: int) -> None:
        """Compile at most 64 phrase actions from a worker-built profile."""
        del fingerprint
        actions: list[SkillAction] = []
        self._solo_profile_present = profile is not None
        self._solo_profile_aligned = bool(profile is not None and profile.aligned)
        self._solo_duration = float(profile.duration) if profile is not None else 0.0
        if profile is not None and profile.aligned:
            for phrase in profile.phrases:
                if not phrase.aligned or not phrase.bars or phrase.bars < 1:
                    continue
                if phrase.section_strength < 0.55:
                    continue
                bar_s = (phrase.end - phrase.start) / max(1, int(phrase.bars))
                if bar_s <= 0:
                    continue
                if phrase.section == "build_candidate":
                    start, attack_end, release_start, end = (
                        phrase.end - 2.0 * bar_s, phrase.end - bar_s,
                        phrase.end, phrase.end + bar_s,
                    )
                    actions.extend((
                        self._action("solo_build_pressure", "solo.low", start, attack_end,
                                     release_start, end, 0.94,
                                     "holding the low end back into a counted build candidate"),
                        self._action("solo_build_pressure", "solo.high", start, attack_end,
                                     release_start, end, 1.04,
                                     "lifting the upper band into a counted build candidate"),
                    ))
                elif phrase.section == "drop_candidate":
                    start, attack_end, release_start, end = (
                        phrase.start, phrase.start + 0.5 * bar_s,
                        phrase.start + bar_s, phrase.start + 2.0 * bar_s,
                    )
                    actions.extend((
                        self._action("solo_drop_reveal", "solo.low", start, attack_end,
                                     release_start, end, 1.05,
                                     "giving the low end a small reveal at a counted drop candidate"),
                        self._action("solo_drop_reveal", "solo.high", start, attack_end,
                                     release_start, end, 0.98,
                                     "making a little room in the upper band at a counted drop candidate"),
                    ))
                elif phrase.section == "breakdown_candidate":
                    actions.append(self._action(
                        "solo_breakdown_breathe", "none", phrase.start,
                        phrase.start, phrase.end, phrase.end, 1.0,
                        "letting the breakdown breathe without an extra EQ move",
                    ))
                elif phrase.section == "groove_candidate":
                    actions.append(self._action(
                        "solo_groove_hold", "none", phrase.start,
                        phrase.start, phrase.end, phrase.end, 1.0,
                        "letting a steady groove carry without an unnecessary move",
                    ))
                if len(actions) >= MAX_PROFILE_ACTIONS:
                    actions = actions[:MAX_PROFILE_ACTIONS]
                    break
        _validate_action_set(actions, MAX_PROFILE_ACTIONS)
        self._solo_actions = tuple(actions)
        self._active_skill = None

    def plan_blend(self, plan, energy: float, ramp_s: float, tail_s: float) -> None:
        """Compile the existing bounded blend ride on the planner worker."""
        self._blend_plan_id = id(plan)
        self._blend_actions = ()
        self._active_skill = None
        if getattr(plan, "kind", "") != "blend":
            if getattr(plan, "kind", "") == "echo":
                self._active_skill = {
                    "id": "echo_out", "name": SKILL_CATALOG["echo_out"].name,
                    "label": SKILL_CATALOG["echo_out"].explanation,
                    "reason": SKILL_CATALOG["echo_out"].purpose,
                    "context": "transition", "start": float(plan.drop),
                    "end": float(plan.done),
                }
            return
        beat = max(0.001, float(plan.beat))
        swap = float(plan.drop) + float(plan.length) / 2.0
        lo = float(plan.drop) + 2.0 * float(ramp_s)
        hi = swap + float(tail_s) - 2.0 * min(float(ramp_s), float(tail_s) / 2.0)
        if hi - lo < 16.0 * beat:
            return
        energy = max(0.0, min(1.0, float(energy)))
        actions = [
            self._action("blend_headroom_ride", "out.gain", lo, lo + beat,
                         hi - beat, hi, STAGE_MULTIPLIER,
                         "keeping both records a little under the soft limiter"),
            self._action("blend_headroom_ride", "in.gain", lo, lo + beat,
                         hi - beat, hi, STAGE_MULTIPLIER,
                         "keeping both records a little under the soft limiter"),
            self._action("blend_upper_exchange", "upper_pair", lo, lo + beat,
                         hi - beat, hi, 0.06 + 0.06 * energy,
                         "trading a little upper-band prominence every eight bars",
                         mode="upper_exchange", cycle_s=TRADE_BARS * 4.0 * beat),
        ]
        if energy >= 0.45:
            depth = 0.12 * energy
            actions.append(self._action(
                "blend_air_handoff", "out.high",
                swap - 4.0 * beat, swap - beat, swap, swap + 2.0 * beat,
                depth, "easing the outgoing upper band toward the bass handoff",
                mode="air_handoff",
            ))
        _validate_action_set(actions, MAX_BLEND_ACTIONS)
        self._blend_actions = tuple(actions)

    def cancel_blend(self) -> None:
        self._blend_plan_id = None
        self._blend_actions = ()
        self._active_skill = None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self._active_skill = None

    def manual_override(self, slot: Optional[int], name: str, at: float,
                        bar_s: float) -> None:
        """Give the human ownership of a lane and release Kaia's move over a bar."""
        name = str(name).lower()
        if name in ("low", "mid", "high"):
            keys: tuple[tuple[object, str], ...] = ((slot, name),)
        elif name in ("trim", "fader"):
            keys = ((slot, "gain"),)
        elif name in ("master", "xfader"):
            keys = (("all", "gain"),)
        else:
            return
        release = ManualRelease(float(at), float(at) + max(0.25, float(bar_s)))
        for key in keys:
            self._manual_overrides.add(key)
            self._manual_release[key] = release
        self._active_skill = {
            "id": "manual_override", "name": "Manual takeover",
            "label": "manual control owns this lane; Kaia's move is easing out",
            "reason": f"manual {name} control", "context": "manual",
            "start": float(at), "end": release.end,
        }

    def hand_back_all(self) -> None:
        """Explicit booth hand-back: clear manual ownership and resume skills."""
        self._manual_overrides.clear()
        self._manual_release.clear()
        self.enabled = True
        self._active_skill = None

    def _manual_fade(self, slot: int, lane: str, factors: np.ndarray,
                     times: np.ndarray) -> np.ndarray:
        key = (slot, lane)
        gain_key = (slot, "gain")
        global_gain = ("all", "gain")
        if key not in self._manual_overrides and gain_key not in self._manual_overrides                 and global_gain not in self._manual_overrides:
            return factors
        release = self._manual_release.get(
            key, self._manual_release.get(gain_key, self._manual_release.get(global_gain))
        )
        if release is None:
            return np.ones_like(times, dtype=np.float32)
        fade = 1.0 - _ease((times - release.start) / max(0.001, release.end - release.start))
        return (1.0 + (factors - 1.0) * fade).astype(np.float32)

    def mask_solo_fallback(self, factors: tuple[np.ndarray, ...], times: np.ndarray,
                           slot: int) -> tuple[np.ndarray, ...]:
        lanes = ("low", "mid", "high")
        return tuple(self._manual_fade(slot, lane, np.asarray(factor, dtype=np.float32), times)
                     for lane, factor in zip(lanes, factors))

    def render_solo(self, times: np.ndarray, slot: int) -> tuple[tuple[np.ndarray, ...], str, str, bool]:
        """Return EQ factors, truthful label, skill id, and whether profile evidence handled this time."""
        ones = np.ones_like(times, dtype=np.float32)
        identity = (ones.copy(), ones.copy(), ones.copy())
        if not self.enabled:
            return identity, "", "", True
        if not self._solo_profile_present or not self._solo_profile_aligned:
            return identity, "", "", False
        now = float(times[-1]) if len(times) else 0.0
        if now > self._solo_duration:
            return identity, "", "", False
        factors = [ones.copy(), ones.copy(), ones.copy()]
        active: list[SkillAction] = []
        for action in self._solo_actions:
            if action.lane != "none" and action.start <= now + 0.04 and action.end >= float(times[0]):
                lane = action.lane.split(".", 1)[1]
                idx = {"low": 0, "mid": 1, "high": 2}[lane]
                multiplier = _factor(action, times)
                factors[idx] *= self._manual_fade(slot, lane, multiplier, times)
                active.append(action)
            elif action.lane == "none" and action.start <= now < action.end:
                active.append(action)
        if active:
            chosen = active[-1]
            spec = SKILL_CATALOG[chosen.skill_id]
            label = chosen.reason
            self._active_skill = {
                "id": chosen.skill_id, "name": spec.name, "label": label,
                "reason": spec.purpose, "context": "solo",
                "start": chosen.start, "end": chosen.end,
            }
            return tuple(factors), label, chosen.skill_id, True
        self._active_skill = None
        return tuple(factors), "", "", True

    def render_blend(self, plan, times: np.ndarray, out_slot: int,
                     in_slot: int) -> tuple[tuple[np.ndarray, ...], str, str]:
        """Evaluate only this plan's bounded actions at the current PCM frame."""
        ones = np.ones_like(times, dtype=np.float32)
        identity = tuple(ones.copy() for _ in range(6))
        if not self.enabled or self._blend_plan_id != id(plan):
            return identity, "", ""
        if getattr(plan, "kind", "") == "echo":
            active = self._active_skill or {}
            return identity, str(active.get("label", "")), "echo_out"
        if getattr(plan, "kind", "") != "blend":
            return identity, "", ""
        factors = [ones.copy() for _ in range(6)]
        active: list[SkillAction] = []
        now = float(times[-1]) if len(times) else 0.0
        for action in self._blend_actions:
            if action.start > now + 0.04 or action.end < float(times[0]):
                continue
            if action.lane == "out.gain":
                value = self._manual_fade(out_slot, "gain", _factor(action, times), times)
                for i in range(3):
                    factors[i] *= value
            elif action.lane == "in.gain":
                value = self._manual_fade(in_slot, "gain", _factor(action, times), times)
                for i in range(3, 6):
                    factors[i] *= value
            elif action.lane == "upper_pair":
                incoming_high = _factor(action, times)
                outgoing_high = 2.0 - incoming_high
                factors[2] *= self._manual_fade(out_slot, "high", outgoing_high, times)
                factors[5] *= self._manual_fade(in_slot, "high", incoming_high, times)
            elif action.lane == "out.high":
                factors[2] *= self._manual_fade(out_slot, "high", _factor(action, times), times)
            active.append(action)
        if active:
            chosen = active[-1]
            spec = SKILL_CATALOG[chosen.skill_id]
            self._active_skill = {
                "id": chosen.skill_id, "name": spec.name,
                "label": chosen.reason, "reason": spec.purpose,
                "context": "blend", "start": chosen.start, "end": chosen.end,
            }
            label = " · ".join(dict.fromkeys(action.reason for action in active))
            return tuple(factors), label, chosen.skill_id
        self._active_skill = None
        return tuple(factors), "", ""

    def report_legacy(self, label: str, start: float, end: float) -> None:
        if not label:
            self._active_skill = None
            return
        spec = SKILL_CATALOG["solo_legacy_phrase_eq"]
        self._active_skill = {
            "id": "solo_legacy_phrase_eq", "name": spec.name,
            "label": label, "reason": spec.purpose, "context": "solo",
            "start": float(start), "end": float(end),
        }

    def clear_active(self) -> None:
        self._active_skill = None

    def snapshot(self) -> dict:
        return {
            "enabled": self.enabled,
            "active": dict(self._active_skill) if self._active_skill else None,
            "profile_loaded": self._solo_profile_present,
            "profile_aligned": self._solo_profile_aligned,
            "solo_actions": len(self._solo_actions),
            "blend_actions": len(self._blend_actions),
            "manual_overrides": sorted((str(slot), lane)
                                       for slot, lane in self._manual_overrides),
            "catalog": sorted(SKILL_CATALOG),
        }

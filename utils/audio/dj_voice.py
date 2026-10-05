"""What Kaia says about her DJing, for the booth's feed — from her real decisions.

Every line is built from what the mixer actually did: the record it picked and
why (key, tempo, how many bars the measurement agreed on), the plan and any
measured nudge, a switch and its reason, a set's progress. No model is called
(§7: the music engine makes none); the wording varies by template so the feed
reads like her, not a log.
"""
from __future__ import annotations

import random
from typing import Optional

from utils.audio import library

_pick = random.choice


def _key_move(a: Optional[str], b: Optional[str]) -> str:
    step = library.key_step(a, b)
    if not a or not b or step is None:
        return ""
    if step == 0:
        return _pick([f"same key, {b} — nothing to fight over", f"both in {b}, so the melodies sit on each other",
                      f"{b} into {b}. no clash to manage"])
    if step == 1:
        return _pick([f"{a} to {b}, one step round the wheel", f"a neighbour on the wheel, {a} → {b}",
                      f"{a} → {b}: close enough that the change feels like a lift, not a jolt"])
    if step == 2:
        return _pick([f"{a} to {b} is a bigger move — an energy shift", f"{a} → {b}, two steps; it'll change the colour of the room"])
    return _pick([f"{a} → {b} isn't a friendly key move, but the beats lock", f"keys are far apart ({a}, {b}) — the drums carry it"])


def now_playing(rec, why: Optional[dict] = None, set_pos: Optional[tuple] = None) -> str:
    bpm = f"{rec.bpm:.0f} bpm" if rec.bpm else "unknown tempo"
    head = _pick([f"{rec.title}{' — ' + rec.artist if rec.artist else ''}. {bpm}, {rec.key or '?'}.",
                  f"on air: {rec.title}. {bpm}{', ' + rec.key if rec.key else ''}.",
                  f"{rec.title} has the room now. {bpm}."])
    tail = ""
    if set_pos:
        i, n = set_pos
        tail = (" " + _pick([f"{i} of {n} in the set.", f"track {i} of {n}.", f"{n - i} left after this one."])
                if i < n else " " + _pick(["last one in the set.", "that's the end of this set."]))
    return head + tail


def chose_next(prev, rec, edge: Optional[dict], in_set: bool) -> str:
    move = _key_move(prev.key, rec.key)
    if edge:
        agree, bars = edge.get("agree"), edge.get("bars")
        measured = _pick([f"measured it against this one — the kicks agree in {agree} of {bars} bars",
                          f"i checked: {agree}/{bars} bars line up kick for kick",
                          f"the grids say it locks; the audio agrees, {agree} of {bars} bars"]) if agree and bars else \
            "measured to lock with this one"
        lead = _pick(["next is", "lining up", "coming next:", "i'll bring in"])
        line = f"{lead} {rec.title}. {measured}"
        if move:
            line += f"; {move}"
        return line + "." + (" " + _pick(["staying with the set.", "next in the set."]) if in_set else "")
    return _pick([f"next is {rec.title}. nothing left in the crate locks with this one, so it'll be a clean switch on the bar.",
                  f"{rec.title} after this — no measured partner, so i'll cut on the bar rather than lay two grooves over each other."])


def planned(plan, nxt_title: str) -> str:
    if plan.kind == "blend":
        bars = round(plan.length / plan.beat / 4) if plan.beat else 0
        s = _pick([f"blending into {nxt_title} over {bars} bars. highs first, bass swap halfway.",
                   f"{bars} bars to bring {nxt_title} in — i'll ride both up in the middle.",
                   f"planned: {bars}-bar blend into {nxt_title}, bass hands over on the halfway bar."])
        if "moved" in (plan.check or ""):
            raw = plan.check.rsplit("moved", 1)[-1].strip().split(" ")[0]
            try:
                v = float(raw)
            except ValueError:
                v = 0.0
            ms, way = f"{abs(v):.0f}", ("earlier" if v < 0 else "later")
            s += " " + _pick([f"the beat grids were off; started it {ms} ms {way} so the kicks land together.",
                              f"moved it {ms} ms {way} — the ticks said one thing, the kicks another.",
                              f"{ms} ms {way} than the grid said. measured, not guessed."])
        return s
    if plan.fallback == "unlocked":
        return _pick([f"{nxt_title} doesn't lock with this — no common pulse. clean switch on the bar, no overlap.",
                      f"measured {nxt_title} against this and the kicks never agree. switching on the bar instead of forcing it."])
    if plan.fallback == "tempo":
        return f"{nxt_title} is too far off in tempo to blend. switching on the bar."
    return _pick([f"switching to {nxt_title} on the bar.", f"clean cut into {nxt_title}."])


def set_started(i: Optional[int], n: int, lo: float, hi: float) -> str:
    name = f"set {i}" if i else "the set"
    return _pick([f"opening {name}: {n} records, {lo:.0f}–{hi:.0f} bpm. every transition in it is measured.",
                  f"{name}. {n} tracks, {lo:.0f} to {hi:.0f} bpm, every one of them locks into the next."])


def hand_load(who: str, title: str) -> str:
    return _pick([f"{who or 'you'} loaded {title}. your deck — i'll keep the other one going.",
                  f"{title} on the free deck. go on then."])

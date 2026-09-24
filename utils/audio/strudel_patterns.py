"""The genres, as arranged tracks.

Each genre is a `tracks.Track`: parts that all exist from the first bar, and a
form that says when each one plays and how its filters and levels move. The
groove is up on bar one — a dance track that opens on a bare kick for twenty
seconds is a click track — and the energy is shaped the way a DJ set is:
groove, build (snare roll, noise riser, filters opening), drop on the one with
a crash, breakdown, build, second drop, outro.

`@KEY@` is replaced by the pass's key, so every melodic part is written in
scale degrees (`n("0 3 7").scale("@KEY@3:minor")`) and a new pass can move key
without rewriting a figure. A part with a list of sounds picks one per pass.

Samples come from what the Strudel REPL prebakes (the tidal drum machines,
VCSL, the General MIDI soundfonts); the break genres also load the full
Dirt-Samples set from GitHub for real breakbeats. Every function used is in
the bundle — tools/maintenance/audition_tracks.py plays each section and
measures it, because Strudel fails silently on anything it cannot parse.
"""
from __future__ import annotations

import re

from utils.audio.tracks import Part, Track

# Single quotes: Strudel parses a double-quoted string as mini-notation, so the
# "/" in the URL became a division and the whole program failed to evaluate.
DIRT = "samples('github:tidalcycles/dirt-samples')"

# ── forms ────────────────────────────────────────────────────────────────

DANCE = [("intro", 8), ("groove", 16), ("build", 8), ("drop", 16),
         ("break", 16), ("build2", 8), ("drop2", 24), ("outro", 8)]
DANCE_LABELS = {
    "intro": "straight in", "groove": "settling into the groove",
    "build": "building", "drop": "drop", "break": "breakdown",
    "build2": "here it comes again", "drop2": "second drop", "outro": "bringing it down",
}
# The whole mix sits lower before the first drop and falls away in the outro,
# so the drop is the loudest thing in the track.
DANCE_ENERGY = {"intro": 0.7, "groove": 0.82, "build": (0.82, 1.0), "outro": (0.85, 0.55)}
CHILL = [("intro", 4), ("a", 16), ("b", 16), ("break", 8), ("a2", 16), ("b2", 16), ("outro", 4)]
CHILL_LABELS = {"intro": "easing in", "a": "the groove", "b": "opening up",
                "break": "a moment of space", "a2": "back in", "b2": "all of it", "outro": "fading"}
DRIFT = [("bed", 8), ("bloom", 8), ("deep", 8), ("glow", 8), ("bloom2", 8), ("fade", 4)]
DRIFT_LABELS = {"bed": "a bed of sound", "bloom": "something opens", "deep": "going deeper",
                "glow": "light coming through", "bloom2": "opening again", "fade": "letting it go"}

DROPS = "drop drop2"
# Bars a groove part plays: all of it, except the breakdown and the pre-drop
# silence at the end of each build.
KICK_BARS = {"intro": 1, "groove": 1, "build": "11111100", "drop": 1,
             "build2": "11110000", "drop2": 1, "outro": 1}
GROOVE_UP = "intro groove build drop build2 drop2 outro"


# ── parts every dance track shares ───────────────────────────────────────

def snare_roll(bank: str, sample: str = "sd") -> Part:
    """The build: a snare that doubles its rate every couple of bars."""
    return Part("roll", f's("{sample}").bank("{bank}").room(0.25).o(2)',
                play="build build2",
                auto={"fast": {"build": "2 2 4 4 8 8 16 16", "build2": "4 4 8 8 16 16 32 32", "default": 1},
                      "gain": {"build": (0.18, 0.62), "build2": (0.22, 0.7), "default": 0.4}},
                say="snare roll")


def riser() -> Part:
    """White noise opening bar by bar into the drop."""
    return Part("riser", 's("white").attack(0.02).release(0.05).hpf(300).room(0.4).pan(sine.slow(2)).o(6)',
                play="build build2",
                auto={"lpf": {"build": (500, 11000), "build2": (500, 12000), "default": 2000},
                      "gain": {"build": (0.03, 0.26), "build2": (0.04, 0.3), "default": 0.1}},
                say="riser")


def crash(bank: str) -> Part:
    """A crash on the first beat of each drop."""
    return Part("crash", f's("cr").bank("{bank}").gain(0.45).room(0.5).o(6)',
                play={"drop": "10", "drop2": "10", "groove": "10"}, say="crash")


def kick(bank: str, extra: str = "", pattern: str = "bd*4") -> Part:
    """Four on the floor, out for the breakdown and the last two bars of each build."""
    return Part("kick", f's("{pattern}").bank("{bank}"){extra}.o(1)', play=KICK_BARS, say="kick")


# ── the genres ───────────────────────────────────────────────────────────

PSYTRANCE = Track(
    name="psytrance", bpm=145, keys=("e", "f", "f#", "d"),
    blurb="rolling K-B-B-B bassline, acid line, FM zaps, big breakdown",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("RolandTR909", ".shape(0.45).lpf(4000).gain(1.08)"),
        Part("bass", [
            'n("[~ 0 0 0]*4").scale("@KEY@1:minor").s("sawtooth").lpq(9).lpenv(2.6).lpa(0.001).lpd(0.07)'
            '.attack(0.001).decay(0.085).sustain(0).release(0.03).distort(0.35).gain(0.9)'
            '.duck("1").duckdepth(0.95).duckattack(0.03).o(3)',
            'n("[~ 0 0 0]*4").add(n("<0!3 [0 0 1 -2]>")).scale("@KEY@1:minor").s("sawtooth").lpq(10)'
            '.lpenv(2.8).lpd(0.07).attack(0.001).decay(0.085).sustain(0).release(0.03).distort(0.4).gain(0.9)'
            '.duck("1").duckdepth(0.95).duckattack(0.03).o(3)',
        ], play=KICK_BARS,
            auto={"lpf": {"intro": (240, 420), "build": (420, 900), "build2": (420, 1000), "default": 460}},
            say="rolling bass"),
        Part("hats", 's("hh*16").bank("RolandTR909").gain("0.32 0.12 0.22 0.12").hpf(6000).pan(0.55).o(2)',
             play="groove build drop drop2 outro", say="hats"),
        Part("ohat", 's("[~ oh]*4").bank("RolandTR909").gain(0.3).cut(1).o(2)',
             play="intro groove drop build2 drop2", say="open hats"),
        Part("perc", 's("rim(5,16,2)").bank("RolandTR909").gain(0.28).delay(0.3).delaytime(0.1875).delayfeedback(0.35).pan(sine.slow(3)).o(2)',
             play="drop drop2", say="rims"),
        Part("acid", [
            'n("0 0 [12 0] 3 0 7 0 [10 12]").scale("@KEY@2:minor").s("sawtooth").lpq(17).lpenv(3.5).lpd(0.12)'
            '.decay(0.14).sustain(0.15).release(0.05).distort(0.5).delay(0.3).delaytime(0.1875).delayfeedback(0.4).gain(0.36).o(4)',
            'n("0 [~ 0] 7 0 [3 0] 0 [12 10] 7").scale("@KEY@2:minor").s("sawtooth").lpq(18).lpenv(4).lpd(0.1)'
            '.decay(0.13).sustain(0.1).release(0.05).distort(0.5).delay(0.3).delaytime(0.1875).delayfeedback(0.45).gain(0.36).o(4)',
        ], play="groove build drop build2 drop2",
            auto={"lpf": {"groove": (300, 1500), "build": (1500, 4500), "drop": 2600, "build2": (900, 4800), "drop2": 3200}},
            say="acid line"),
        Part("zaps", 'n("<[0 ~ 7 ~] [~ 12 ~ 10] [3 ~ ~ 7] [~ 5 12 ~]>*2").scale("@KEY@4:minor").s("square")'
             '.fm(3).fmh(2.01).fmdecay(0.08).decay(0.12).sustain(0).lpf(5000).room(0.4).delay(0.45).delaytime(0.25)'
             '.delayfeedback(0.5).gain(0.24).pan(sine.slow(4)).o(4)',
             play="drop2", say="FM zaps"),
        Part("arp", 'n("{0 7 3 10 5 12}%16").scale("@KEY@4:minor").s("triangle").decay(0.12).sustain(0)'
             '.delay(0.55).delaytime(0.1875).delayfeedback(0.55).room(0.6).gain(0.26).o(5)',
             play="break build2 drop2",
             auto={"lpf": {"break": (1200, 5000), "default": 5000}}, say="arp"),
        Part("pad", 'n("<[0,2,4] [-2,0,2] [-3,-1,1] [-1,1,3]>").scale("@KEY@3:minor").s("supersaw").detune(0.35)'
             '.attack(1.2).release(3).lpf(1800).room(0.8).roomsize(6).duck("1").duckdepth(0.5).o(5)',
             play="break build2",
             auto={"gain": {"break": (0.12, 0.3), "build2": (0.3, 0.2), "default": 0.25}}, say="pad"),
        snare_roll("RolandTR909"), riser(), crash("RolandTR909"),
    ])

TECHNO = Track(
    name="techno", bpm=132, keys=("a", "f", "g", "d"),
    blurb="909 techno: offbeat rumble bass, hypnotic stab, ride, acid in the second drop",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("RolandTR909", ".shape(0.3).gain(1.1)"),
        Part("bass", 'n("[~ 0]*4").scale("@KEY@1:minor").s("sawtooth").lpf(230).lpq(5).decay(0.16).sustain(0.15)'
             '.release(0.08).distort(0.25).gain(0.8).duck("1").duckdepth(0.9).o(3)',
             play=GROOVE_UP, say="rumble bass"),
        Part("hats", 's("hh*16").bank("RolandTR909").gain("0.3 0.1 0.2 0.1").pan(0.4).o(2)',
             play="intro groove build drop drop2 outro", say="hats"),
        Part("ohat", 's("[~ oh]*4").bank("RolandTR909").gain(0.28).cut(1).o(2)',
             play="groove drop build2 drop2", say="open hats"),
        Part("clap", 's("~ cp ~ cp").bank("RolandTR909").gain(0.42).room(0.35).o(2)',
             play="groove drop drop2", say="clap"),
        Part("ride", 's("rd*4").bank("RolandTR909").gain(0.14).pan(0.7).o(2)',
             play="drop drop2", say="ride"),
        Part("perc", 's("lt(3,8,2) mt(3,8,5)").bank("RolandTR909").gain(0.3).room(0.3).delay(0.25).delaytime(0.1875).o(2)',
             play="groove drop drop2", say="toms"),
        Part("stab", [
            'n("[0,2,4]").scale("@KEY@3:minor").struct("x(3,8,2)").s("sawtooth").lpq(6).lpenv(3).lpd(0.1)'
            '.decay(0.16).sustain(0).room(0.5).delay(0.4).delaytime(0.1875).delayfeedback(0.55).gain(0.3).o(4)',
            'n("[0,3,4]").scale("@KEY@3:minor").struct("x(5,16,1)").s("sawtooth").lpq(6).lpenv(3).lpd(0.1)'
            '.decay(0.16).sustain(0).room(0.5).delay(0.4).delaytime(0.25).delayfeedback(0.5).gain(0.28).o(4)',
        ], play="groove build drop break build2 drop2",
            auto={"lpf": {"groove": (400, 1600), "build": (1600, 5000), "drop": 2800, "break": 1400,
                          "build2": (1200, 5500), "drop2": 3000}}, say="stab"),
        Part("acid", 'n("0 0 12 0 [0 3] 0 7 [0 10]").scale("@KEY@2:minor").s("sawtooth").lpq(16).lpenv(3.5).lpd(0.11)'
             '.decay(0.13).sustain(0.1).distort(0.45).gain(0.3).o(4)',
             play="drop2", auto={"lpf": {"drop2": (500, 3200)}}, say="acid"),
        Part("pad", 'n("<[0,2,4,6] [0,2,4,6] [-2,0,2,4] [-2,0,2,4]>").scale("@KEY@3:minor").s("gm_pad_sweep:3").attack(1).release(4)'
             '.room(0.8).roomsize(5).gain(0.4).o(5)',
             play="break build2", say="pad"),
        snare_roll("RolandTR909"), riser(), crash("RolandTR909"),
    ])

HOUSE = Track(
    name="house", bpm=124, keys=("c", "f", "g", "d", "a"),
    blurb="house: 909 kit, swung shaker, piano stabs, bouncing bass, choir in the break",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("RolandTR909", ".gain(1.0)"),
        Part("clap", 's("~ cp ~ cp").bank("RolandTR909").gain(0.45).room(0.25).o(2)',
             play=GROOVE_UP, say="clap"),
        Part("ohat", 's("[~ oh]*4").bank("RolandTR909").gain(0.26).cut(1).o(2)',
             play=GROOVE_UP, say="open hat"),
        Part("shaker", 's("hh*16").bank("RolandTR808").gain("0.2 0.08 0.14 0.08").swingBy(1/3, 4).pan(0.6).o(2)',
             play="groove build drop drop2", say="shaker"),
        Part("bass", [
            'n("<[0 ~ 0 ~ ~ 0 ~ 0] [~ 0 ~ 7 ~ 0 ~ ~]>").scale("@KEY@2:minor").s("sawtooth").lpf(700).lpq(7)'
            '.lpenv(2).lpd(0.15).decay(0.22).sustain(0.1).release(0.1).gain(0.78).duck("1").duckdepth(0.55).o(3)',
            'n("<[0 ~ ~ 0 ~ 0 ~ ~] [3 ~ ~ 3 ~ 3 ~ 5]>").scale("@KEY@2:minor").s("gm_synth_bass_1:1").lpf(1400)'
            '.gain(0.9).duck("1").duckdepth(0.5).o(3)',
        ], play=GROOVE_UP, say="bass"),
        Part("piano", [
            'n("<[0,2,4,6] [3,5,7,9] [5,7,9,11] [4,6,8,10]>").scale("@KEY@3:minor").struct("~ x ~ x ~ [x x] ~ x")'
            '.s("piano").room(0.3).gain(0.55).o(4)',
            'n("<[0,2,4,6] [-2,0,2,4] [-3,-1,1,3] [-1,1,3,5]>").scale("@KEY@3:minor").struct("x ~ ~ x ~ ~ x ~")'
            '.s("piano").room(0.3).gain(0.55).o(4)',
        ], play="groove build drop break build2 drop2",
            auto={"lpf": {"groove": (800, 6000), "break": 3000, "default": 7000}}, say="piano"),
        Part("choir", 'n("<[0,2,4] [3,5,7] [5,7,9] [4,6,8]>").scale("@KEY@4:minor").s("gm_choir_aahs:3")'
             '.attack(0.4).release(2).room(0.8).roomsize(5).gain(0.45).o(5)',
             play="break build2 drop2", say="choir"),
        Part("top", 'n("<[7 ~ 9 ~] [11 ~ 9 7]>*2").scale("@KEY@5:minor").s("kalimba").delay(0.4).delaytime(0.1875)'
             '.delayfeedback(0.5).room(0.5).gain(0.4).pan(sine.slow(3)).o(5)',
             play="drop2", say="kalimba"),
        snare_roll("RolandTR909", "cp"), riser(), crash("RolandTR909"),
    ])

DEEPHOUSE = Track(
    name="deephouse", bpm=120, keys=("f", "a", "d", "g"),
    blurb="deep house: soft kick, shuffled rim and hats, Rhodes minor nines, warm sub, pluck",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("RolandTR808", ".lpf(900).gain(1.05)", "bd*4"),
        Part("rim", 's("~ rim ~ [~ rim] ~ rim ~ ~").bank("RolandTR808").gain(0.3).room(0.2).o(2)',
             play=GROOVE_UP, say="rim"),
        Part("hats", 's("[~ hh]*4, hh*16").bank("RolandTR909").gain("0.22 0.08").swingBy(1/6, 8).hpf(5000).o(2)',
             play="groove build drop drop2 outro", say="hats"),
        Part("clap", 's("~ cp ~ cp").bank("RolandTR808").gain(0.32).room(0.45).o(2)',
             play="drop drop2", say="clap"),
        Part("bass", 'n("<[0 ~ ~ 0 ~ ~ 0 ~] [-2 ~ ~ -2 ~ 0 ~ ~]>").scale("@KEY@1:minor").s("sine").decay(0.4)'
             '.sustain(0.3).release(0.2).gain(0.95).duck("1").duckdepth(0.5).o(3)',
             play=GROOVE_UP, say="sub"),
        Part("keys", 'n("<[0,2,4,6,8] [-2,0,2,4,6] [-3,-1,1,3,5] [-1,1,3,5,7]>").scale("@KEY@3:minor")'
             '.struct("~ [~ x] ~ ~ x ~ ~ ~").s("gm_epiano1:4").room(0.4).gain(0.6).o(4)',
             play="groove build drop break build2 drop2",
             auto={"lpf": {"groove": (900, 5000), "break": 2500, "default": 5000}}, say="rhodes"),
        Part("pluck", 'n("{0 4 7 9 11}%8").scale("@KEY@4:minor").s("triangle").decay(0.15).sustain(0)'
             '.delay(0.5).delaytime(0.375).delayfeedback(0.5).room(0.5).gain(0.25).pan(sine.slow(5)).o(5)',
             play="drop break drop2", say="pluck"),
        Part("pad", 'n("<[0,2,4] [0,2,4] [-2,0,2] [-2,0,2]>").scale("@KEY@3:minor").s("gm_pad_warm:4").attack(1.5).release(3)'
             '.room(0.7).gain(0.35).o(5)', play="break build2 drop2", say="pad"),
        snare_roll("RolandTR808", "cp"), riser(), crash("RolandTR909"),
    ])

TRANCE = Track(
    name="trance", bpm=138, keys=("a", "g", "b", "d", "e"),
    blurb="trance: rolling bass, trance-gated supersaw chords, anthem lead, huge breakdown",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("RolandTR909", ".shape(0.3).gain(1.05)"),
        Part("bass", 'n("<[~ 0 0 0]*4 [~ 0 0 0]*4 [~ -2 -2 -2]*4 [~ -4 -4 -4]*4>").scale("@KEY@1:minor").s("sawtooth")'
             '.lpf(500).lpq(6).lpenv(2).lpd(0.08).decay(0.1).sustain(0).gain(0.85).duck("1").duckdepth(0.9).o(3)',
             play=GROOVE_UP, say="rolling bass"),
        Part("hats", 's("[~ hh]*4, hh*16").bank("RolandTR909").gain("0.3 0.1").o(2)',
             play="intro groove build drop drop2 outro", say="hats"),
        Part("clap", 's("~ cp ~ cp").bank("RolandTR909").gain(0.4).room(0.35).o(2)',
             play="groove drop drop2", say="clap"),
        Part("gate", 'n("<[0,2,4] [0,2,4] [-2,0,2] [-4,-2,0]>").scale("@KEY@3:minor").s("supersaw").detune(0.4)'
             '.struct("x*16").gain("0.36 0.1 0.26 0.1 0.36 0.1 0.26 0.16").decay(0.1).sustain(0).release(0.05)'
             '.duck("1").duckdepth(0.6).o(4)',
             play="groove build drop build2 drop2",
             auto={"lpf": {"groove": (500, 2500), "build": (2500, 7000), "drop": 5000, "build2": (1500, 7000), "drop2": 6000}},
             say="trance gate"),
        Part("lead", [
            'n("<[4 ~ 4 7 ~ 4 2 ~] [0 ~ 0 2 ~ 4 2 ~] [-1 ~ -1 0 ~ 2 0 ~] [-3 ~ -3 -1 ~ 0 -1 ~]>").scale("@KEY@4:minor")'
            '.s("supersaw").detune(0.5).attack(0.01).decay(0.2).sustain(0.4).release(0.3).lpf(5000)'
            '.delay(0.3).delaytime(0.1875).delayfeedback(0.4).room(0.4).gain(0.36).o(4)',
            'n("<[7 ~ 4 ~ 2 4 ~ 7] [9 ~ 7 ~ 4 ~ 2 ~] [7 ~ 4 ~ 2 4 ~ 0] [2 ~ 0 ~ -1 ~ 0 ~]>").scale("@KEY@4:minor")'
            '.s("supersaw").detune(0.5).attack(0.01).decay(0.2).sustain(0.4).release(0.3).lpf(5000)'
            '.delay(0.3).delaytime(0.1875).delayfeedback(0.4).room(0.4).gain(0.36).o(4)',
        ], play="drop break drop2", auto={"lpf": {"break": (1200, 4000), "default": 5000}}, say="lead"),
        Part("pad", 'n("<[0,2,4] [0,2,4] [-2,0,2] [-4,-2,0]>").scale("@KEY@3:minor").s("gm_synth_strings_1:1")'
             '.attack(1).release(3).room(0.8).roomsize(6).gain(0.4).o(5)',
             play="break build2 drop2", say="strings"),
        snare_roll("RolandTR909"), riser(), crash("RolandTR909"),
    ])

DRUMNBASS = Track(
    name="drumnbass", bpm=174, keys=("f", "e", "g", "d"),
    blurb="drum and bass: a real break under a two-step kit, reese bass, liquid keys in the break",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        Part("break", 's("breaks165").fit().gain(0.65).hpf(200).o(2)',
             play=GROOVE_UP, say="break"),
        Part("kit", 's("bd ~ ~ ~ ~ ~ ~ ~ ~ ~ bd ~ ~ ~ ~ ~, ~ ~ ~ ~ sd ~ ~ ~ ~ ~ ~ ~ sd ~ ~ ~").bank("RolandTR909")'
             '.gain(0.9).shape(0.2).o(1)',
             play={"intro": 1, "groove": 1, "build": "11111100", "drop": 1, "build2": "11110000", "drop2": 1, "outro": 1},
             say="two-step"),
        Part("hats", 's("hh*8").bank("RolandTR909").gain("0.22 0.14").pan(0.6).o(2)',
             play="groove drop drop2", say="hats"),
        Part("reese", [
            'n("<0 0 -2 -4>").scale("@KEY@1:minor").s("supersaw").detune(0.7).lpf(320).lpq(6).distort(0.35)'
            '.gain(0.55).duck("1").duckdepth(0.7).o(3)',
            'n("<[0 ~ ~ 0 ~ ~ 0 ~] [-2 ~ ~ -2 ~ ~ 3 ~] [-4 ~ ~ -4 ~ ~ 0 ~] [0 ~ ~ 0 ~ ~ -1 ~]>").scale("@KEY@1:minor")'
            '.s("supersaw").detune(0.7).lpf(360).lpq(6).distort(0.35).decay(0.3).sustain(0.5).gain(0.55)'
            '.duck("1").duckdepth(0.7).o(3)',
        ], play="groove build drop build2 drop2",
            auto={"lpf": {"build": (300, 1400), "build2": (300, 1600), "default": 340}}, say="reese"),
        Part("sub", 'n("<0 0 -2 -4>").scale("@KEY@1:minor").s("sine").gain(0.75).duck("1").duckdepth(0.6).o(3)',
             play=GROOVE_UP, say="sub"),
        Part("keys", 'n("<[0,2,4,6] [0,2,4,6] [-2,0,2,4] [-2,0,2,4] [-4,-2,0,2] [-4,-2,0,2] [-3,-1,1,3] [-3,-1,1,3]>").scale("@KEY@3:minor").s("gm_epiano1:4")'
             '.struct("x ~ ~ x ~ ~ ~ ~").room(0.5).gain(0.5).o(4)',
             play="intro break build2 drop2", say="keys"),
        Part("pad", 'n("<[0,2,4] [0,2,4] [-2,0,2] [-2,0,2]>").scale("@KEY@3:minor").s("gm_pad_halo:2").attack(1).release(3)'
             '.room(0.8).gain(0.4).o(5)', play="break build2", say="pad"),
        Part("bells", 'n("{0 4 7 11 9}%8").scale("@KEY@5:minor").s("tubularbells").room(0.6)'
             '.delay(0.4).delaytime(0.1875).gain(0.25).o(5)', play="drop2", say="bells"),
        snare_roll("RolandTR909"), riser(), crash("RolandTR909"),
    ])

ACID = Track(
    name="acid", bpm=128, keys=("a", "e", "f", "g"),
    blurb="acid house: a 303 line whose filter and drive climb through the set, 909 underneath",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("RolandTR909", ".shape(0.25).gain(1.05)"),
        Part("hats", 's("[~ hh]*4").bank("RolandTR909").gain(0.3).o(2)', play=GROOVE_UP, say="hats"),
        Part("ohat", 's("[~ oh]*4").bank("RolandTR909").gain(0.2).cut(1).late(0.0625).o(2)',
             play="drop drop2", say="open hats"),
        Part("clap", 's("~ cp ~ cp").bank("RolandTR909").gain(0.4).room(0.3).o(2)',
             play="groove drop drop2", say="clap"),
        Part("acid", [
            'n("0 0 [12 0] 0 [3 0] 0 [7 10] 0").scale("@KEY@2:minor").s("sawtooth").lpq(20).lpenv(3).lpd(0.12)'
            '.decay(0.15).sustain(0.1).gain("0.42 0.3 0.42 0.3").delay(0.25).delaytime(0.1875).o(3)',
            'n("0 [~ 0] 12 [0 3] ~ 0 [10 7] 0").scale("@KEY@2:minor").s("sawtooth").lpq(20).lpenv(3).lpd(0.12)'
            '.decay(0.15).sustain(0.1).gain("0.42 0.3 0.42 0.3").delay(0.25).delaytime(0.1875).o(3)',
        ], play="intro groove build drop break build2 drop2 outro",
            auto={"lpf": {"intro": (250, 500), "groove": (500, 1800), "build": (1800, 5500), "drop": 3000,
                          "break": (800, 2000), "build2": (1500, 6000), "drop2": (3000, 5000), "outro": (2000, 400)},
                  "distort": {"drop": 0.4, "drop2": 0.7, "build2": 0.5, "default": 0.2}},
            say="303"),
        Part("bass", 'n("[0 ~ ~ 0]*2").scale("@KEY@1:minor").s("sine").gain(0.8).duck("1").duckdepth(0.6).o(3)',
             play="groove drop drop2", say="sub"),
        Part("stab", 'n("[0,3,7]").scale("@KEY@3:minor").struct("~ x ~ ~ ~ x ~ ~").s("square").decay(0.1)'
             '.sustain(0).lpf(2500).room(0.5).delay(0.5).delaytime(0.1875).delayfeedback(0.6).gain(0.22).o(4)',
             play="break build2 drop2", say="stab"),
        snare_roll("RolandTR909"), riser(), crash("RolandTR909"),
    ])

BREAKBEAT = Track(
    name="breakbeat", bpm=136, keys=("e", "g", "a", "d"),
    blurb="breakbeat: a chopped break, wobbling bass, hoover stabs, big drops",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        Part("break", ['s("breaks152").fit().gain(0.75).o(2)',
                       's("breaks152").fit().chop(16).rev().sometimesBy(0.3, x => x.speed(1.5)).gain(0.7).o(2)'],
             play=GROOVE_UP.replace("build ", ""), say="break"),
        Part("kit", 's("bd ~ ~ bd ~ ~ bd ~, ~ ~ sd ~ ~ ~ sd ~").bank("RolandTR808").gain(0.85).o(1)',
             play={"groove": 1, "build": "11111100", "drop": 1, "build2": "11110000", "drop2": 1}, say="kick and snare"),
        Part("bass", 'n("<0 0 3 -2>").scale("@KEY@1:minor").s("sawtooth").struct("x ~ x x ~ x ~ x")'
             '.lpf(sine.range(200, 1600).fast(2)).lpq(10).distort(0.3).gain(0.6).duck("1").duckdepth(0.7).o(3)',
             play="intro groove build drop build2 drop2 outro", say="wobble bass"),
        Part("hoover", 'n("<[0 ~ ~ 0] [3 ~ ~ 2]>").scale("@KEY@3:minor").s("supersaw").detune(0.9).decay(0.25)'
             '.sustain(0.3).lpf(3000).room(0.4).gain(0.32).o(4)',
             play="drop drop2", say="hoover"),
        Part("pad", 'n("<[0,2,4] [0,2,4] [-2,0,2] [-2,0,2]>").scale("@KEY@3:minor").s("gm_pad_sweep:3").attack(1).release(3)'
             '.room(0.7).gain(0.4).o(5)', play="break build2", say="pad"),
        Part("fx", 'n("<0 ~ ~ ~>").scale("@KEY@5:minor").s("square").fm(8).fmh(3.3).decay(0.4).sustain(0)'
             '.delay(0.6).delaytime(0.375).delayfeedback(0.65).room(0.6).gain(0.2).o(5)',
             play="intro break drop2", say="fx"),
        snare_roll("RolandTR808"), riser(), crash("RolandTR909"),
    ])

DUB = Track(
    name="dub", bpm=140, keys=("a", "g", "d", "e"),
    blurb="dub: steppers half-time, sub bassline, echoing skank chords, melodica, a siren in the space",
    form=CHILL, labels=CHILL_LABELS,
    parts=[
        Part("kick", 's("bd*4").bank("RolandTR808").lpf(800).gain(1.0).o(1)',
             play="intro a b a2 b2 outro", say="steppers kick"),
        Part("snare", 's("~ ~ rim ~").bank("RolandTR808").gain(0.55).room(0.4).delay(0.5).delaytime(0.375)'
             '.delayfeedback(0.6).o(2)', play="a b a2 b2", say="rim on three"),
        Part("hats", 's("[~ hh]*4").bank("RolandTR808").gain(0.2).o(2)', play="b b2", say="hats"),
        Part("bass", ['n("<[0 ~ 0 ~ 3 ~ 2 ~] [0 ~ ~ 0 5 ~ 3 ~]>").scale("@KEY@1:minor").s("sine").decay(0.35)'
                      '.sustain(0.5).gain(1.0).o(3)',
                      'n("<[0 ~ ~ 0 ~ 3 ~ ~] [5 ~ 3 ~ 2 ~ 0 ~]>").scale("@KEY@1:minor").s("sine").decay(0.35)'
                      '.sustain(0.5).gain(1.0).o(3)'],
             play="a b break a2 b2", say="bassline"),
        Part("skank", 'n("[~ [0,2,4]]*2").scale("@KEY@3:minor").s("gm_drawbar_organ:4").decay(0.12).sustain(0)'
             '.delay(0.45).delaytime(0.375).delayfeedback(0.55).room(0.3).gain(0.45).o(4)',
             play="intro a b a2 b2", auto={"delayfeedback": {"b": 0.65, "b2": 0.7, "default": 0.55}},
             say="skank"),
        Part("melodica", 'n("<[4 ~ ~ 2 ~ 0 ~ ~] ~ [2 ~ 4 ~ 7 ~ ~ ~] ~>").scale("@KEY@4:minor").s("harmonica")'
             '.room(0.5).delay(0.4).delaytime(0.375).delayfeedback(0.5).gain(0.5).o(5)',
             play="b b2", say="melodica"),
        Part("siren", 'note("a5").s("square").vib(4).vibmod(7).attack(0.05).decay(1.2).sustain(0.2)'
             '.lpf(2800).room(0.7).delay(0.6).delaytime(0.75).delayfeedback(0.6).o(6)',
             play={"break": "1000", "b2": "00000001"}, say="dub siren"),
        Part("space", 's("~ ~ ~ [~ cp]").bank("RolandTR808").gain(0.4).room(0.9).roomsize(8)'
             '.delay(0.7).delaytime(0.375).delayfeedback(0.72).o(6)', play="break", say="echo throw"),
    ])

LOFI = Track(
    name="lofi", bpm=80, keys=("d", "f", "a", "c"),
    blurb="lofi: dusty swung boom-bap, jazzy Rhodes nines, upright bass, vinyl crackle",
    form=CHILL, labels=CHILL_LABELS,
    parts=[
        Part("kick", 's("bd ~ ~ [~ bd] ~ ~ bd ~").bank("RolandTR808").lpf(1200).gain(0.95).o(1)',
             play="a b a2 b2", say="kick"),
        Part("snare", 's("~ ~ sd ~ ~ ~ sd ~").bank("AkaiMPC60").lpf(3000).gain(0.55).room(0.2).o(2)',
             play="a b a2 b2", say="snare"),
        Part("hats", 's("hh*8").bank("AkaiMPC60").gain("0.2 0.1").swingBy(1/6, 4).lpf(6000).o(2)',
             play="a b a2 b2 outro", say="hats"),
        Part("keys", ['n("<[0,2,4,6,8] [-3,-1,1,3,5] [-2,0,2,4,6] [-4,-2,0,2,4]>").scale("@KEY@3:dorian")'
                      '.struct("x ~ ~ [~ x] ~ ~ x ~").s("gm_epiano1:4").lpf(2200).room(0.35).gain(0.6).o(4)',
                      'n("<[0,2,4,6] [3,5,7,9] [1,3,5,7] [4,6,8,10]>").scale("@KEY@3:dorian")'
                      '.struct("x ~ ~ x ~ [~ x] ~ ~").s("gm_epiano1:4").lpf(2200).room(0.35).gain(0.6).o(4)'],
             play="all", say="rhodes"),
        Part("bass", 'n("<[0 ~ ~ 4] [-3 ~ ~ 1] [-2 ~ 2 ~] [-4 ~ ~ -1]>").scale("@KEY@1:dorian").s("gm_acoustic_bass:1")'
             '.gain(0.9).o(3)', play="a b break a2 b2", say="upright bass"),
        Part("melody", 'n("<[~ 4 ~ ~ 6 ~ 4 ~] ~ [~ 2 ~ 4 ~ ~ 1 ~] ~>").scale("@KEY@4:dorian").s("vibraphone")'
             '.room(0.5).delay(0.3).delaytime(0.375).gain(0.4).o(5)', play="b b2", say="vibes"),
        Part("crackle", 's("white*16").degradeBy(0.88).decay(0.004).sustain(0).hpf(3500).gain(0.12).o(6)',
             play="all", say="vinyl"),
    ])

TRIPHOP = Track(
    name="triphop", bpm=88, keys=("c", "d", "e", "a"),
    blurb="trip-hop: a slowed break, heavy sub, eerie strings and Rhodes, crackle",
    form=CHILL, labels=CHILL_LABELS,
    parts=[
        Part("break", 's("breaks125").fit().lpf(3500).gain(0.8).o(2)', play="a b a2 b2", say="slowed break"),
        Part("kick", 's("bd ~ ~ ~ ~ ~ bd ~").bank("RolandTR808").gain(0.85).o(1)', play="a b a2 b2", say="kick"),
        Part("bass", 'n("<[0 ~ ~ ~ ~ ~ -2 ~] [-3 ~ ~ ~ -2 ~ ~ ~]>").scale("@KEY@1:minor").s("sine").decay(0.6)'
             '.sustain(0.6).gain(1.0).o(3)', play="a b break a2 b2", say="sub"),
        Part("strings", 'n("<[0,2,4] [-2,0,3] [-3,0,2] [-1,1,4]>").scale("@KEY@3:minor").s("gm_string_ensemble_1:3")'
             '.attack(0.8).release(2.5).room(0.7).gain(0.4).o(4)', play="intro b break b2 outro", say="strings"),
        Part("keys", 'n("<[0,2,4,6] ~ [-2,0,2,4] ~>").scale("@KEY@3:minor").s("gm_epiano2:4").room(0.5)'
             '.delay(0.35).delaytime(0.5).delayfeedback(0.45).gain(0.5).o(4)', play="a a2 b2", say="rhodes"),
        Part("bells", 'n("<[4 ~ ~ ~] [~ ~ 7 ~] [6 ~ ~ ~] [~ ~ 2 ~]>").scale("@KEY@5:minor").s("gm_celesta:4")'
             '.room(0.8).delay(0.5).delaytime(0.75).delayfeedback(0.5).gain(0.35).o(5)', play="b break b2", say="celesta"),
        Part("crackle", 's("white*16").degradeBy(0.9).decay(0.004).sustain(0).hpf(3000).gain(0.14).o(6)',
             play="all", say="crackle"),
    ])

SYNTHWAVE = Track(
    name="synthwave", bpm=104, keys=("a", "e", "d", "c"),
    blurb="synthwave: LinnDrum with a gated snare, driving octave bass, big pads, a saw lead",
    form=DANCE, labels=DANCE_LABELS, energy=DANCE_ENERGY,
    parts=[
        kick("LinnDrum", ".gain(1.0)"),
        Part("snare", 's("~ sd ~ sd").bank("LinnDrum").room(0.7).roomsize(4).gain(0.55).o(2)',
             play="groove drop drop2 outro", say="gated snare"),
        Part("hats", 's("hh*8").bank("LinnDrum").gain("0.25 0.14").o(2)', play=GROOVE_UP, say="hats"),
        Part("bass", 'n("<[0 12]*8 [0 12]*8 [-4 8]*8 [-2 10]*8>").scale("@KEY@1:minor").s("sawtooth")'
             '.lpf(900).lpq(4).decay(0.12).sustain(0.2).gain(0.55).duck("1").duckdepth(0.4).o(3)',
             play=GROOVE_UP, auto={"lpf": {"intro": (400, 900), "build": (900, 2000), "default": 1000}},
             say="octave bass"),
        Part("pad", 'n("<[0,2,4] [0,2,4] [-4,-2,0] [-2,0,2]>").scale("@KEY@3:minor").s("gm_synth_strings_1:1")'
             '.attack(0.5).release(2).room(0.6).gain(0.42).o(5)', play="groove drop break build2 drop2", say="pad"),
        Part("lead", ['n("<[4 ~ 2 ~ 0 ~ 2 4] [7 ~ ~ 4 ~ ~ 2 ~] [0 ~ -1 ~ 0 ~ 2 ~] [4 ~ ~ ~ ~ ~ ~ ~]>")'
                      '.scale("@KEY@4:minor").s("gm_lead_2_sawtooth:4").room(0.5).delay(0.35).delaytime(0.375)'
                      '.delayfeedback(0.4).gain(0.45).o(4)'],
             play="drop break drop2", say="lead"),
        Part("arp", 'n("[0 2 4 7]*4").scale("@KEY@4:minor").s("square").decay(0.08).sustain(0).lpf(3000)'
             '.delay(0.3).delaytime(0.1875).gain(0.2).pan(sine.slow(4)).o(5)',
             play="build drop2 build2", say="arp"),
        snare_roll("LinnDrum"), riser(), crash("RolandTR909"),
    ])

BERLINSCHOOL = Track(
    name="berlinschool", bpm=112, keys=("a", "d", "e", "g"),
    blurb="berlin school: interlocking sequencers under slow filter sweeps, a pad, a pulse",
    form=[(name, bars * 2) for name, bars in DRIFT], labels=DRIFT_LABELS,
    parts=[
        Part("seq", 'n("0 7 12 7 3 7 12 15").fast(2).scale("@KEY@2:minor").s("sawtooth").lpq(8).decay(0.12)'
             '.sustain(0).delay(0.35).delaytime(0.1875).delayfeedback(0.45).gain(0.4).o(3)',
             play="all", auto={"lpf": {"bed": (400, 900), "bloom": (900, 3000), "deep": 700, "glow": (700, 2500),
                                       "bloom2": (1500, 4000), "fade": (2000, 400)}}, say="sequencer"),
        Part("seq2", 'n("{0 3 7 10 7 3}%12").scale("@KEY@3:minor").s("triangle").decay(0.1).sustain(0)'
             '.pan(sine.slow(6)).room(0.4).gain(0.3).o(4)', play="bloom glow bloom2", say="second sequence"),
        Part("pulse", 'n("0*8").scale("@KEY@1:minor").s("sawtooth").lpf(300).decay(0.1).sustain(0.2).gain(0.6).o(3)',
             play="bloom deep glow bloom2", say="pulse"),
        Part("kick", 's("bd*4").bank("RolandTR808").lpf(600).gain(0.85).o(1)', play="glow bloom2", say="kick"),
        Part("pad", 'n("<[0,2,4] [0,2,4] [-2,0,2] [-2,0,2] [-3,0,2] [-3,0,2] [-1,1,3] [-1,1,3]>").scale("@KEY@3:minor").s("gm_pad_poly:3")'
             '.attack(2).release(4).room(0.8).roomsize(6).gain(0.45).o(5)', play="all", say="pad"),
        Part("choir", 'n("<[0,4] [0,4] [0,4] [0,4] [2,6] [2,6] [2,6] [2,6]>").scale("@KEY@4:minor").s("gm_synth_choir:3").attack(3).release(4)'
             '.room(0.9).gain(0.3).o(6)', play="deep bloom2", say="choir"),
    ])

AMBIENT = Track(
    name="ambient", bpm=64, keys=("d", "e", "g", "a", "c"),
    blurb="ambient: drones and bowed pads, glass and bells drifting, wind, a few piano notes",
    form=DRIFT, labels=DRIFT_LABELS,
    parts=[
        Part("drone", 'n("<[0,4] [0,4] [0,4] [0,4] [-2,2] [-2,2] [-3,2] [-3,2]>").scale("@KEY@2:major").s("gm_pad_bowed:2").attack(3).release(6)'
             '.room(0.9).roomsize(8).gain(0.5).o(3)', play="all", say="drone"),
        Part("halo", 'n("<[0,2,4,6] [0,2,4,6] [0,2,4,6] [0,2,4,6] [-1,1,3,5] [-1,1,3,5] [-1,1,3,5] [-1,1,3,5]>").scale("@KEY@3:major").s("gm_pad_halo:2").attack(4).release(6)'
             '.room(0.9).gain(0.35).o(4)', play="bloom deep glow bloom2", say="halo"),
        Part("bells", 'n("{0 4 2 6 7 4 9}%4").scale("@KEY@5:major").s("vibraphone").degradeBy(0.35)'
             '.room(0.9).delay(0.5).delaytime(0.75).delayfeedback(0.55).pan(sine.slow(7)).gain(0.32).o(5)',
             play="bloom glow bloom2", say="bells"),
        Part("glass", 'n("<[0,4] [2,6] [4,7] [2,5]>").scale("@KEY@5:major").s("gm_tinkle_bell").room(0.9)'
             '.delay(0.5).delaytime(0.75).delayfeedback(0.5).pan(perlin.slow(5)).o(5)',
             play="deep glow fade", say="glass"),
        Part("piano", 'n("<[4 ~ ~ 2] [~ 6 ~ ~] [2 ~ 4 ~] [~ ~ 7 ~]>").scale("@KEY@4:major").s("piano").room(0.9)'
             '.roomsize(8).delay(0.4).delaytime(1).delayfeedback(0.4).o(6)', play="glow bloom2", say="piano"),
        Part("chimes", 's("handchimes").n("<0 2 1 3>").room(0.9).pan(sine.slow(3)).o(6)',
             play={"bloom": "10001000", "bloom2": "10001000"}, say="chimes"),
        Part("wind", 's("pink").attack(2).release(3).lpf(sine.range(300, 1200).slow(16)).gain(0.07).pan(sine.slow(9)).o(6)',
             play="all", say="wind"),
    ])


TRACKS = [PSYTRANCE, TECHNO, HOUSE, DEEPHOUSE, TRANCE, DRUMNBASS, ACID, BREAKBEAT,
          DUB, LOFI, TRIPHOP, SYNTHWAVE, BERLINSCHOOL, AMBIENT]

GENRES: dict[str, dict] = {
    t.name: {"bpm": f"~{t.bpm:g}", "cpm": f"{t.bpm:g}/4", "blurb": t.blurb, "track": t}
    for t in TRACKS
}

DEFAULT_GENRE = "house"


_SYNTHS = {"sawtooth", "square", "triangle", "sine", "supersaw", "white", "pink", "brown"}
_KIT = {"bd", "sd", "hh", "oh", "cp", "rim", "cr", "rd", "lt", "mt", "ht", "cb", "perc", "sh"}


def warmup_program() -> str:
    """A silent program that loads every sample and soundfont the tracks use.

    Run once when the engine starts. Two things were silent without it: the
    break genres, whose `samples("github:...")` header made the first program
    of a set wait on a download past the click that starts audio, so Strudel's
    clock never started; and any soundfont's first bar, while it downloaded.
    """
    names = set()
    for t in TRACKS:
        for part in t.parts:
            for sound in ([part.sound] if isinstance(part.sound, str) else part.sound):
                for m in re.finditer(r'\bs\("([^"]+)"\)', sound):
                    for tok in re.split(r"[\s,\[\]<>*~]+", m.group(1)):
                        # Keep a soundfont's `:k`: each variant is its own file,
                        # and warming variant 0 leaves the one that plays cold.
                        tok = re.sub(r"[(!].*$", "", tok)
                        if tok and not tok[0].isdigit() and tok.split(":")[0] not in _SYNTHS | _KIT:
                            names.add(tok)
    listed = " ".join(sorted(names))
    # A sampled instrument (piano, VCSL) is one file per note zone, fetched the
    # first time a note needs it; one trigger loads one zone, and the rest of
    # the melody played silence while its zones downloaded. A chromatic run
    # through each of them touches every zone the tracks can reach.
    sampled = " ".join(sorted(n for n in names if not n.startswith(("gm_", "breaks"))))
    chromatic = " ".join(f"{p}{o}" for o in range(2, 7)
                         for p in ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"))
    lines = [DIRT, "setcpm(60/4)", f'$: s("[{listed}]").gain(0.0001)']
    if sampled:
        lines.append(f'$: note("{chromatic}").s("[{sampled.replace(" ", ",")}]").gain(0.0001)')
    return "\n".join(lines)


def genre_names() -> list[str]:
    return list(GENRES)


def describe(genre: str) -> str:
    g = GENRES.get(genre, GENRES[DEFAULT_GENRE])
    return f"{genre} ({g['bpm']} bpm) — {g['blurb']}"


def total_seconds(genre: str) -> float:
    return GENRES[genre]["track"].seconds()

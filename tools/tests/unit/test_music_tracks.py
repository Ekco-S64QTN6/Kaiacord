"""The arranged-track music engine: form, arrangement, passes, clock."""
import random

import pytest

from utils.audio.strudel_patterns import DANCE, GENRES, TRACKS
from utils.audio.tracks import (Part, Track, TrackPerformance, _mask_bars, _per_bar,
                                arrangement, check, sequence)

DANCE_TRACKS = [t for t in TRACKS if t.form == DANCE]


def _toy():
    return Track(name="toy", bpm=120, blurb="", keys=("a", "c"),
                 form=[("intro", 2), ("drop", 4), ("break", 2)],
                 parts=[Part("kick", 's("bd*4")', play="intro drop"),
                        Part("lead", ['n("0 3").scale("@KEY@4:minor")', 'n("0 7").scale("@KEY@4:minor")'],
                             play={"drop": "10"}, auto={"lpf": {"drop": (400, 1000), "default": 800}})])


def test_a_sequence_is_run_length_encoded_and_rotated_to_the_anchor():
    assert sequence([1, 1, 0, 0, 0, 1], 0) == "<1!2 0!3 1>"
    # Anchored at 2: Strudel's cycle 2 must play bar 0 of the form.
    rotated = sequence([1, 1, 0, 0, 0, 1], 2)
    items = []
    for tok in rotated.strip("<>").split():
        v, _, n = tok.partition("!")
        items += [v] * int(n or 1)
    assert items[2] == "1" and items[4] == "0" and items[1] == "1"


def test_ramps_step_once_per_bar_and_masks_pad_with_their_last_value():
    t = _toy()
    assert _per_bar(t, {"drop": (400, 1000), "default": 800}, 800) == [800, 800, 400, 600, 800, 1000, 800, 800]
    assert _mask_bars(t, {"drop": "10"}) == [0, 0, 1, 0, 0, 0, 0, 0]
    assert _mask_bars(t, "intro drop") == [1, 1, 1, 1, 1, 1, 0, 0]


def test_the_arrangement_is_appended_as_per_bar_sequences():
    t = _toy()
    chain, plays = arrangement(t, t.parts[1], 0)
    assert plays
    assert '.lpf("<800!2 400 600 800 1000 800!2>")' in chain
    assert '.mask("<0!2 1 0!5>")' in chain


def test_a_part_that_never_plays_is_left_out():
    t = _toy()
    t.parts.append(Part("ghost", 's("hh")', play="nowhere"))
    assert "ghost" not in TrackPerformance(t, random.Random(1)).lanes


def test_a_new_pass_moves_key_and_can_change_figures():
    p = TrackPerformance(_toy(), random.Random(3))
    first = p.key
    p.next_pass()
    assert p.key != first
    assert f'scale("{p.key}4:minor")' in p.code()


def test_the_clock_places_bars_and_sections():
    p = TrackPerformance(_toy(), random.Random(1), anchor=10)
    info = p.update(10.0 + 3.5)             # bar 3 of the form, inside the drop
    assert (info["bar"], info["section"], info["new_pass"]) == (3, "drop", False)
    info = p.update(10.0 + 8.2)             # past the end: pass two begins
    assert info["new_pass"] and info["pass"] == 1
    assert p.cycles_to_next_pass(10.0 + 7.5) == pytest.approx(0.5)


def test_status_lists_only_what_is_sounding_in_this_section():
    p = TrackPerformance(_toy(), random.Random(1))
    p.update(0.5)                            # intro: kick only
    assert p.describe()["lanes"] == ["kick"]


def test_a_dj_edit_keeps_the_arrangement():
    """Kaia's requests re-render the program; the form must not restart."""
    from utils.audio import dj
    p = TrackPerformance(GENRES["techno"]["track"], random.Random(1), anchor=37)
    before = p.code()
    dj.apply_request("darker", p, GENRES["techno"]["cpm"])
    after = p.code()
    import re
    masks = lambda code: re.findall(r'\.mask\("([^"]*)"\)', code)
    assert masks(before) == masks(after)


@pytest.mark.parametrize("track", TRACKS, ids=lambda t: t.name)
def test_every_track_is_well_formed(track):
    assert check(track) == []
    p = TrackPerformance(track, random.Random(0))
    code = p.code()
    assert code.count("(") == code.count(")")
    assert code.count("setcpm(") == 1
    assert "@KEY@" not in code
    assert 1.5 * 60 <= track.seconds() <= 6 * 60


@pytest.mark.parametrize("track", DANCE_TRACKS, ids=lambda t: t.name)
def test_a_dance_track_has_a_groove_on_bar_one(track):
    """The old model opened on a bare kick for twenty seconds."""
    sounding = [p.name for p in track.parts if _mask_bars(track, p.play)[0]]
    assert len(sounding) >= 3, sounding
    assert any(n in sounding for n in ("kick", "kit", "break"))
    assert any(n in sounding for n in ("bass", "sub", "reese", "acid"))


@pytest.mark.parametrize("track", DANCE_TRACKS, ids=lambda t: t.name)
def test_a_dance_track_builds_and_drops(track):
    names = [p.name for p in track.parts]
    assert {"roll", "riser", "crash"} <= set(names)
    crash = next(p for p in track.parts if p.name == "crash")
    bars = _mask_bars(track, crash.play)
    starts = {s: sum(b for _, b in track.form[:i]) for i, (s, _) in enumerate(track.form)}
    assert bars[starts["drop"]] == 1 and bars[starts["drop2"]] == 1
    # The last bar before each drop is silent under the kick: that is what makes the drop land.
    kick = next(p for p in track.parts if p.name in ("kick", "kit"))
    kb = _mask_bars(track, kick.play)
    assert kb[starts["drop"] - 1] == 0 and kb[starts["drop2"] - 1] == 0
    assert kb[starts["drop"]] == 1


def test_reanchoring_moves_the_form_and_nothing_else():
    """Jumping to a section must not drop a solo or a DJ edit: the first
    calibration run measured the full mix for every "solo" because of it."""
    p = TrackPerformance(GENRES["techno"]["track"], random.Random(1))
    p.soloed = "hats"
    p.lanes["bass"].set_param("lpf", "300")
    key, sounds = p.key, {n: l.base for n, l in p.lanes.items()}
    p.reanchor(40)
    assert p.anchor == 40 and p.soloed == "hats" and p.key == key
    assert {n: l.base for n, l in p.lanes.items()} == sounds
    assert ".lpf(300)" in p.code()
    assert sum(1 for l in p.code().splitlines() if l.startswith("$:")) == 1


@pytest.mark.parametrize("track", DANCE_TRACKS, ids=lambda t: t.name)
def test_the_drop_is_the_loudest_part_of_a_dance_track(track):
    """The kick and bass carry every section's loudness, so the whole mix
    rides an energy curve: lower before the first drop, falling in the outro."""
    curve = _per_bar(track, {"default": 1, **track.energy}, 1)
    starts = {s: sum(b for _, b in track.form[:i]) for i, (s, _) in enumerate(track.form)}
    assert curve[starts["drop"]] == 1 and curve[starts["drop2"]] == 1
    assert curve[0] < curve[starts["groove"]] < 1
    p = TrackPerformance(track, random.Random(0))
    assert '.velocity("<' in p.code()
    p.energy = False
    p.reanchor(0)
    assert ".velocity(" not in p.code()

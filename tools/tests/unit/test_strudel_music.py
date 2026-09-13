"""
Tests for the Strudel-backed !music engine.

Anything that can be checked without a browser lives here. The one thing that
genuinely cannot — whether a pattern makes a sound — is
tools/maintenance/verify_strudel_patterns.py, which plays every state of every
genre and measures the audio. That split exists because a pattern Strudel
cannot parse does not raise: evaluate() returns, the scheduler logs a start,
the AudioContext reports "running", and the result is silence.
"""

import random
import re

import pytest

from utils.audio.performance import (ADD, CLEAR, DROP, FX, SET, SOLO, Lane,
                                     Move, Performance, build)
from utils.audio.strudel_patterns import (DEFAULT_GENRE, GENRES, describe,
                                          genre_names, total_seconds)

BEAT_GENRES = [g for g in GENRES if "kick" in GENRES[g]["lanes"]
               or "break" in GENRES[g]["lanes"] or "drums" in GENRES[g]["lanes"]]


# ── Lane editing ─────────────────────────────────────────────────────

def test_a_lane_renders_as_a_dollar_lane():
    assert Lane("b", 's("bd*4")').render() == '$: s("bd*4")'


def test_a_muted_lane_uses_the_underscore_prefix():
    assert Lane("b", 's("bd*4")').render(muted=True) == '_$: s("bd*4")'


def test_effects_chain_onto_a_playing_lane():
    lane = Lane("b", 'n("0*8").s("supersaw")')
    lane.add_fx(".lpf(400)")
    lane.add_fx('.duck("1").duckdepth(0.5)')
    assert lane.render() == '$: n("0*8").s("supersaw").lpf(400).duck("1").duckdepth(0.5)'


def test_the_same_effect_is_not_chained_twice():
    """Otherwise a long performance ends up with .lpf() six times over."""
    lane = Lane("b", 'n("0*8")')
    assert lane.add_fx(".lpf(400)") is True
    assert lane.add_fx(".lpf(900)") is False
    assert lane.render().count(".lpf(") == 1


def test_a_parameter_is_edited_in_place():
    """The whole point of the model: "lower the depth of the duck to 0.8" has
    to change one number on a line that is already playing, not restate it."""
    lane = Lane("b", 'n("0*8")')
    lane.add_fx('.duck("1").duckdepth(0.5)')
    lane.set_param("duckdepth", "0.8")
    assert ".duckdepth(0.8)" in lane.render()
    assert ".duckdepth(0.5)" not in lane.render()


def test_setting_a_parameter_that_is_in_the_base_works():
    lane = Lane("b", 'n("0*8").s("supersaw").lpf(300)')
    lane.set_param("lpf", "1200")
    assert ".lpf(1200)" in lane.render() and ".lpf(300)" not in lane.render()


def test_setting_an_absent_parameter_appends_it():
    lane = Lane("b", 'n("0*8")')
    lane.set_param("gain", "0.5")
    assert lane.render().endswith(".gain(0.5)")


# ── Performance ──────────────────────────────────────────────────────

def _perf():
    return Performance(
        cpm="120/4",
        lanes={"kick": 's("bd*4")', "bass": 'n("0*8")', "pad": 'n("<0,3>")'},
        script=[
            Move(ADD, "kick", seconds=10, say="kick"),
            Move(ADD, "bass", seconds=10, say="bass"),
            Move(FX, "bass", arg=".lpf(400)", seconds=10, say="filter"),
            Move(SET, "bass", arg="lpf", value="900", seconds=10, say="open it"),
            Move(SOLO, "bass", seconds=10, say="isolate"),
            Move(CLEAR, seconds=10, say="back"),
            Move(DROP, "kick", seconds=10, say="drop kick"),
        ])


def test_only_live_lanes_are_emitted():
    p = _perf()
    assert 's("bd*4")' in p.code()
    assert 'n("0*8")' not in p.code()
    p.advance(11)
    assert 'n("0*8")' in p.code()


def test_tempo_appears_exactly_once():
    p = _perf()
    for _ in range(len(p.script)):
        assert p.code().count("setcpm(") == 1
        p.advance(11)


def test_consecutive_states_differ_by_little():
    """A section change should read as an edit, not a new program — that is
    what makes it look like live coding rather than a slideshow."""
    p = _perf()
    p.advance(11)                       # kick + bass
    before = p.code()
    p.advance(11)                       # chain .lpf onto bass
    after = p.code()
    assert before != after
    same = sum(1 for a, b in zip(before.split("\n"), after.split("\n")) if a == b)
    assert same >= len(before.split("\n")) - 1, "more than one line changed"


def test_solo_mutes_the_others_without_removing_them():
    p = _perf()
    # The constructor already applies move 0, so four advances lands on SOLO.
    for _ in range(4):
        p.advance(11)
    code = p.code()
    assert "_$: " in code, "nothing was muted"
    assert 'n("0*8")' in code and not re.search(r'_\$: n\("0\*8"\)', code)
    p.advance(11)                       # CLEAR
    assert "_$: " not in p.code()


def test_a_pass_resets_the_accumulated_edits():
    """Without this every lane carries every mutation forever and the second
    pass starts where the first ended."""
    p = _perf()
    for _ in range(len(p.script) + 1):
        p.advance(11)
    assert p.passes == 1
    assert p.lanes["bass"].chain == []


def test_advance_only_fires_when_the_move_is_due():
    p = _perf()
    assert p.advance(4) is False
    assert p.advance(4) is False
    assert p.advance(4) is True


# ── Genre definitions ────────────────────────────────────────────────

def test_there_are_genres_and_a_valid_default():
    assert len(GENRES) >= 10
    assert DEFAULT_GENRE in GENRES


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_every_genre_is_completely_specified(genre):
    g = GENRES[genre]
    assert {"bpm", "cpm", "blurb", "lanes", "script"} <= set(g)
    assert g["lanes"] and g["script"]


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_scripts_only_reference_lanes_that_exist(genre):
    g = GENRES[genre]
    for m in g["script"]:
        if m.get("lane"):
            assert m["lane"] in g["lanes"], f"{genre}: unknown lane {m['lane']!r}"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_every_lane_gets_brought_in(genre):
    g = GENRES[genre]
    added = {m["lane"] for m in g["script"] if m["op"] == ADD}
    assert set(g["lanes"]) - added == set(), \
        f"{genre}: lanes never added: {set(g['lanes']) - added}"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_a_lane_is_only_edited_while_it_is_playing(genre):
    """Chaining an effect onto a lane that has not been added yet is a silent
    no-op in the output and means the edit was wasted."""
    g = GENRES[genre]
    live = set()
    for m in g["script"]:
        if m["op"] == ADD:
            live.add(m["lane"])
        elif m["op"] == DROP:
            live.discard(m["lane"])
        elif m["op"] in (FX, SET):
            assert m["lane"] in live, \
                f"{genre}: edits {m['lane']!r} before it is playing ({m.get('say')!r})"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_the_script_is_mostly_edits_not_just_parts(genre):
    """The complaint that produced this model was that it held kick+hats for
    ages and then swapped whole blocks. A performance should be dominated by
    small changes to what is already sounding."""
    ops = [m["op"] for m in GENRES[genre]["script"]]
    edits = sum(1 for o in ops if o in (FX, SET))
    assert edits >= 5, f"{genre} has only {edits} edit moves"
    assert edits / len(ops) > 0.25, f"{genre} is mostly add/drop, not editing"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_nothing_sits_on_one_state_for_too_long(genre):
    """Holding a bare kick for a minute is the exact complaint."""
    for m in GENRES[genre]["script"]:
        assert m.get("seconds", 20) <= 40, \
            f"{genre}: {m.get('say')!r} holds for {m['seconds']}s"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_every_move_says_what_it_is_doing(genre):
    """The narration is shown in the editor and written to the log; a move
    without one is invisible to whoever is watching."""
    for m in GENRES[genre]["script"]:
        assert m.get("say"), f"{genre}: a {m['op']} move has no narration"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_a_pass_is_long_enough_to_be_a_set(genre):
    assert 240 <= total_seconds(genre) <= 900


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_resonance_stays_reasonable(genre):
    """A high resonance sweeping the top octave is the "swoosh" that was
    painful to listen to."""
    g = GENRES[genre]
    blobs = list(g["lanes"].values()) + [m.get("arg", "") for m in g["script"]] \
        + [m.get("value", "") for m in g["script"] if m.get("arg") == "lpq"]
    for blob in blobs:
        for q in re.findall(r"\.lpq\((\d+(?:\.\d+)?)\)", str(blob)):
            assert float(q) <= 16, f"{genre} sets lpq({q})"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_no_lane_sets_its_own_tempo(genre):
    for name, code in GENRES[genre]["lanes"].items():
        assert "setcpm" not in code, f"{genre}/{name} sets tempo itself"


@pytest.mark.parametrize("genre", BEAT_GENRES)
def test_beat_driven_genres_expose_a_scope(genre):
    """The operator watches the editor while it plays; the scope is how the
    waveform is visible at all."""
    assert any("_scope()" in c for c in GENRES[genre]["lanes"].values()), \
        f"{genre} has no _scope() anywhere"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_each_genre_offers_at_least_one_slider(genre):
    """Sliders are what let a human ride the filter while Kaia plays."""
    g = GENRES[genre]
    text = " ".join(list(g["lanes"].values()) + [m.get("arg", "") for m in g["script"]])
    assert "slider(" in text, f"{genre} exposes nothing to grab"


def test_several_genres_use_vocals():
    voxed = [g for g in GENRES if "vox" in GENRES[g]["lanes"]]
    assert len(voxed) >= 4, f"only {voxed} use vocal samples"


# ── build() ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("genre", sorted(GENRES))
def test_build_walks_the_whole_script_without_error(genre):
    perf = build(GENRES[genre], random.Random(1))
    seen = set()
    for _ in range(len(perf.script)):
        code = perf.code()
        assert code.startswith("setcpm(")
        seen.add(code)
        perf.advance(10_000)
    assert len(seen) > len(perf.script) // 2, "too many identical states"


def test_build_varies_the_timings():
    a = build(GENRES[DEFAULT_GENRE], random.Random(1))
    b = build(GENRES[DEFAULT_GENRE], random.Random(2))
    assert [m.seconds for m in a.script] != [m.seconds for m in b.script]


# ── Command parsing ──────────────────────────────────────────────────

@pytest.mark.parametrize("words,expected", [
    (["!music", "on", "--house"], ("on", "house")),
    (["!music", "--techno"], ("on", "techno")),
    (["!music", "trance"], ("on", "trance")),
    (["!music", "off"], ("off", None)),
    (["!music"], ("status", None)),
    (["!music", "genres"], ("genres", None)),
    (["!music", "on"], ("on", None)),
])
def test_command_parsing(words, expected):
    from utils.commands.music_handler import _parse
    assert _parse(words) == expected


# ── Wiring ───────────────────────────────────────────────────────────

def test_music_is_registered():
    from utils.commands.registry import _build_lookup
    cmd = _build_lookup()["!music"]
    assert cmd.handler.__name__ == "handle_music_command"


def test_shutdown_releases_voice_before_cancelling_tasks():
    from pathlib import Path
    src = Path("utils/infrastructure/system/shutdown_fixed.py").read_text(encoding="utf-8")
    assert "strudel_session" in src
    assert src.index("stop_all") < src.index("cancel_all")


def test_the_page_embeds_the_repl_not_the_slim_bundle():
    """@strudel/web lacks _scope, _pianoroll, slider, trancegate and rlpf, and
    they fail silently there. The REPL component has them."""
    from pathlib import Path
    page = Path("assets/strudel/player.html").read_text(encoding="utf-8")
    assert "strudel-editor" in page
    assert "strudel-repl.js" in page


def test_patterns_are_applied_from_a_real_gesture():
    from pathlib import Path
    page = Path("assets/strudel/player.html").read_text(encoding="utf-8")
    assert "addEventListener('click'" in page
    click = page.index("addEventListener('click'")
    assert "applyPending" in page[click:click + 120]


def test_the_engine_marshals_playwright_onto_one_thread():
    """Playwright's sync API raises "Cannot switch to a different thread"
    anywhere but its creating thread; the session starts the engine on an
    executor and then drives it from the event loop."""
    from pathlib import Path
    src = Path("utils/audio/strudel_engine.py").read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" in src and "_call" in src
    for method in ("_start_impl", "_play_impl", "_stop_impl", "_close_impl"):
        assert method in src


def test_no_strudel_source_is_vendored():
    """Strudel is AGPL-3.0; it is fetched at install time, never committed."""
    import subprocess
    from pathlib import Path
    for name in ("strudel-repl.js", "strudel-web.js"):
        f = Path("assets/strudel") / name
        if f.exists():
            tracked = subprocess.run(["git", "ls-files", str(f)],
                                     capture_output=True, text=True).stdout.strip()
            assert not tracked, f"{name} must not be committed"

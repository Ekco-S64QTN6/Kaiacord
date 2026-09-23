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


def _lanes_of(move) -> list[str]:
    """The lanes a move touches, the way Performance._apply reads them.

    ADD and DROP take a comma-separated list so a genre can open on a whole
    groove instead of a bare kick; these checks have to split it the same way
    or every multi-lane opening reads as one unknown lane.
    """
    return [n.strip() for n in (move.get("lane") or "").split(",") if n.strip()]


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_every_genre_is_completely_specified(genre):
    g = GENRES[genre]
    assert {"bpm", "cpm", "blurb", "lanes", "script"} <= set(g)
    assert g["lanes"] and g["script"]


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_scripts_only_reference_lanes_that_exist(genre):
    g = GENRES[genre]
    for m in g["script"]:
        for _lane in _lanes_of(m):
            assert _lane in g["lanes"], f"{genre}: unknown lane {_lane!r}"


@pytest.mark.parametrize("genre", sorted(GENRES))
def test_every_lane_gets_brought_in(genre):
    g = GENRES[genre]
    added = {l for m in g["script"] if m["op"] == ADD for l in _lanes_of(m)}
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
            live.update(_lanes_of(m))
        elif m["op"] == DROP:
            live.difference_update(_lanes_of(m))
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
    assert _parse(words)[:2] == expected


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


def test_the_editor_is_styled_as_the_hosts_sibling():
    """<strudel-editor> renders nothing inside itself.

    Its connectedCallback does `parentElement.insertBefore(div, nextSibling)`
    and hands StrudelMirror that div, so the editor is the host's SIBLING.
    Styling the host as if it were the editor gave a full-viewport empty box
    and pushed the real editor offscreen — the page looked blank apart from
    the header.
    """
    from pathlib import Path
    page = Path("assets/strudel/player.html").read_text(encoding="utf-8")
    assert "strudel-editor + div" in page, "the sibling is what must be sized"
    assert "strudel-editor{display:none}" in page.replace(" ", "")


def test_human_edits_are_tracked_on_the_real_editor():
    """The keystroke listener sat on <strudel-editor>, which is empty and
    display:none, so `dirty` was never set: human_edited() was permanently
    false and Kaia overwrote every edit at her next move, while the header
    promised she would not."""
    from pathlib import Path
    page = Path("assets/strudel/player.html").read_text(encoding="utf-8")
    assert "ed.addEventListener('keydown'" not in page, \
        "listening on the host element catches nothing"
    assert "ed.nextElementSibling" in page, "edits happen in the sibling root"
    assert "watchEdits()" in page


def test_apply_runs_the_humans_code_when_kaia_did_not_stage_it():
    """`apply` always ran `pending` — Kaia's code — so a person who edited and
    pressed it had their edit replaced by her last pattern."""
    from pathlib import Path
    page = Path("assets/strudel/player.html").read_text(encoding="utf-8")
    assert "k.staged" in page, "the button has to know who staged the code"
    body = page[page.index("function applyPending"):]
    body = body[:body.index("\n      }")]
    assert "repl().code" in body, "the human branch must run what is on screen"

    src = Path("utils/audio/strudel_engine.py").read_text(encoding="utf-8")
    assert "window.__kaia.staged = true" in src, \
        "the engine must mark its own patterns as staged"


def test_the_hint_names_the_evaluate_shortcut():
    """Plain enter inserts a newline, which reads as "apply does nothing"."""
    from pathlib import Path
    page = Path("assets/strudel/player.html").read_text(encoding="utf-8")
    hint = page[page.index('id="hint"'):]
    hint = hint[:hint.index("</span>")]
    assert "enter" in hint.lower() and "ctrl" in hint.lower()


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


# ── The patch re-patches itself between passes ───────────────────────

def test_a_pass_ends_by_repatching_not_restoring():
    """A pass used to end by restoring the original lanes verbatim, so an hour
    of listening was the same set played over and over. The notes inside each
    lane varied; the system never rewrote itself."""
    import random, re
    from utils.audio.performance import build

    g = GENRES["ambient"]
    assert g.get("variants"), "ambient needs a variant palette to re-patch from"

    p = build(g, random.Random(11))
    seen = []
    for _ in range(5):
        for _ in range(len(p.script) + 1):
            p.advance(99_999)
        body = p.lanes["turing1"].base
        seen.append((
            re.search(r'scale\("([^"]+)"', body).group(1),
            re.search(r'\.s\("([^"]+)"', body).group(1),
            re.search(r'mask\("([^"]+)"', body).group(1),
        ))
    assert len(set(seen)) >= 4, f"passes barely differ: {seen}"


def test_the_instrument_family_keeps_moving():
    """Swapping keyed on the *original* token, so once a lane had moved off
    gm_kalimba the key was gone and it froze on its second instrument for the
    rest of the session."""
    import random
    from utils.audio.performance import _apply_variants

    variants = {"swap": {"gm_kalimba": ["gm_kalimba", "gm_vibraphone", "gm_music_box"]}}
    rng = random.Random(3)
    defs = {"turing1": 'n("0").s("gm_kalimba")'}
    instruments = set()
    for _ in range(24):
        defs = _apply_variants(defs, variants, rng)
        instruments.add(defs["turing1"].split('"')[-2])
    assert len(instruments) == 3, f"family stopped moving: {instruments}"


def test_repatching_keeps_every_lane_intact():
    """A mutation that mangles a lane is silence five minutes in, which is the
    worst kind of failure here: nothing errors, the music just thins out."""
    import random
    from utils.audio.performance import build

    g = GENRES["ambient"]
    for seed in range(8):
        p = build(g, random.Random(seed))
        for _ in range((len(p.script) + 1) * 3):
            p.advance(99_999)
        for name, lane in p.lanes.items():
            assert lane.base.strip(), f"seed {seed}: {name} was emptied"
            assert lane.base.count("(") == lane.base.count(")"), \
                f"seed {seed}: {name} has unbalanced parens after re-patching"
            assert lane.base.count('"') % 2 == 0, \
                f"seed {seed}: {name} has an unterminated string"


def test_the_whole_rack_is_playing_within_thirty_seconds():
    """"everything should be playing by 30 seconds in" — the build used to
    introduce one lane at a time over four minutes."""
    g = GENRES["ambient"]
    live, elapsed = set(), 0
    for mv in g["script"]:
        if mv["op"] == ADD:
            live.update(n.strip() for n in mv["lane"].split(","))
        if len(live) == len(g["lanes"]):
            break
        elapsed += mv["seconds"]
    else:
        raise AssertionError("the script never has every lane playing at once")
    assert elapsed <= 30, f"the rack takes {elapsed}s to assemble"


def test_the_rack_is_actually_a_rack():
    """State Azure's point of comparison is a wall of modules. Six voices on
    three clocks is not that."""
    g = GENRES["ambient"]
    assert len(g["lanes"]) >= 12, f"only {len(g['lanes'])} voices"
    euclids = {m.group(0) for b in g["lanes"].values()
               for m in re.finditer(r"\(\d+,\d+\)", b)}
    assert len(euclids) >= 3, f"gates share their timing: {euclids}"


# ── One-off events, re-rolled every pass ─────────────────────────────

@pytest.mark.parametrize("genre", sorted(GENRES))
def test_every_event_names_a_real_lane(genre):
    """The lane check only covered `script`, so a typo in an event pool would
    surface as a move that silently does nothing."""
    g = GENRES[genre]
    for ev in g.get("events", []):
        for lane in _lanes_of(ev):
            assert lane in g["lanes"], f"{genre}: event names unknown lane {lane!r}"


def test_events_differ_from_pass_to_pass():
    """Re-patching changes what the voices are; events change what happens to
    them. Without this every pass walks the same moves in the same order, and
    after an hour the surprises are always in the same places."""
    import random
    from utils.audio.performance import build

    g = GENRES["ambient"]
    assert g.get("events"), "ambient needs an event pool"
    scripted = {m.get("say") for m in g["script"]}

    p = build(g, random.Random(5))
    rolls = []
    for _ in range(4):
        for _ in range(len(p.script) + 1):
            p.advance(99_999)
        rolls.append(tuple(sorted(m.say for m in p.script if m.say not in scripted)))
    assert all(rolls), "some pass got no events at all"
    assert len(set(rolls)) >= 3, f"event rolls barely vary: {rolls}"


def test_an_event_never_fires_before_the_rack_is_up():
    """An event aimed at a lane that is not playing yet is a move nobody
    hears."""
    import random
    from utils.audio.performance import build

    g = GENRES["ambient"]
    scripted = {m.get("say") for m in g["script"]}
    for seed in range(12):
        p = build(g, random.Random(seed))
        for i, mv in enumerate(p.script):
            if mv.say not in scripted:
                assert i >= 3, f"seed {seed}: event at position {i}, before the rack is up"


def test_a_layered_lane_holds_its_loudness_too():
    """`s("a,b:0:0.4")` is two sources with the second at 40%. Compensating by
    blending the two families' ratios cannot hold a weighted sum: measured that
    way the choir lane wandered 2.3x over sixty passes while single-source lanes
    held at 1.00x. The level of the whole lane is the thing to hold."""
    import random
    from utils.audio.performance import _apply_variants, _lane_level

    g = GENRES["ambient"]
    variants = g["variants"]
    levels = {i: l for fam in variants["swap"].values() for i, l in fam.items()}

    layered = [n for n, b in g["lanes"].items()
               if re.search(r'\.s\("[^"]*,[^"]*"', b)]
    assert layered, "expected at least one layered lane to guard"

    defs = {n: g["lanes"][n] for n in layered}
    rng = random.Random(9)
    loud = {n: [] for n in layered}
    for _ in range(40):
        defs = _apply_variants(defs, variants, rng)
        for n, body in defs.items():
            lvl = _lane_level(body, levels)
            gains = re.findall(r"\.gain\(([\d.]+)\)", body)
            if lvl and gains:
                loud[n].append(float(gains[-1]) * lvl)
    # A lane whose sources are plain oscillators (sine, square) has no measured
    # level to hold it to; only the soundfont-backed ones are checkable.
    measurable = {n: h for n, h in loud.items() if h}
    assert measurable, "no layered lane had a measurable level"
    for n, h in measurable.items():
        assert max(h) / min(h) < 1.15, \
            f"{n} drifts {max(h)/min(h):.2f}x across swaps"


def test_a_bernoulli_branch_never_matches_its_lane():
    """bells routes a coin flip to a bright voice or a distant one. A blind
    string replace hit the lane and the branch together, so after one re-patch
    both sides were the same instrument and the gate stopped doing anything."""
    import random
    from utils.audio.performance import _apply_variants

    g = GENRES["ambient"]
    defs = {"bells": g["lanes"]["bells"]}
    rng = random.Random(9)
    for _ in range(30):
        defs = _apply_variants(defs, g["variants"], rng)
        body = defs["bells"]
        main = re.search(r'\.s\("([^"]+)"', body).group(1)
        branch = re.search(r'x=>x\.s\("([^"]+)"', body)
        assert branch and branch.group(1) != main, \
            f"both sides of the gate are {main}"


def test_swapping_an_instrument_holds_its_loudness():
    """Soundfonts are nowhere near level with each other: measured at equal
    gain, gm_vibraphone is 5x gm_kalimba and gm_glockenspiel is 8x quieter than
    gm_celesta. Swapping without compensating meant a voice leapt out or
    vanished at a pass boundary, and an hour in the mix had wandered somewhere
    nobody chose."""
    import random
    from utils.audio.performance import _apply_variants

    variants = GENRES["ambient"]["variants"]
    levels = variants["swap"]["struck"]
    defs = {"turing1": GENRES["ambient"]["lanes"]["turing1"]}
    rng = random.Random(2)

    loudness = []
    for _ in range(24):
        defs = _apply_variants(defs, variants, rng)
        body = defs["turing1"]
        inst = re.search(r'\.s\("([^"]+)"', body).group(1)
        gain = float(re.search(r"\.gain\(([\d.]+)\)", body).group(1))
        assert inst in levels, f"swapped outside the family: {inst}"
        loudness.append(gain * levels[inst])

    spread = max(loudness) / min(loudness)
    assert spread < 1.15, f"loudness drifts {spread:.2f}x across swaps: {loudness[:6]}"


def test_every_swap_family_carries_measured_levels():
    """A family given as a bare list silently loses compensation."""
    for genre, g in GENRES.items():
        for family, members in (g.get("variants", {}).get("swap") or {}).items():
            assert isinstance(members, dict), \
                f"{genre}/{family} has no measured levels, so swaps will jump in volume"
            assert all(isinstance(v, (int, float)) and v > 0 for v in members.values()), \
                f"{genre}/{family} has a non-positive level"


def test_repatching_never_rewrites_a_trigger_rate():
    """A blanket `.slow(N)` substitution also hit the trigger rates: turing1
    went .slow(3) -> .slow(31) and the sub .slow(2) -> .slow(17), so a single
    re-patch made the rack ten times sparser and quietly undid the fix for
    "it takes forever to get going".

    A slow() hanging off a signal is modulation and may be re-rolled. A slow()
    applied to the pattern is tempo and may not."""
    import random
    from utils.audio.performance import _apply_variants

    g = GENRES["ambient"]
    variants = g["variants"]
    rng = random.Random(1)
    defs = {n: g["lanes"][n] for n in ("turing1", "sub", "swell")}

    def trigger_of(body):
        # the slow() that is not attached to a signal
        return re.findall(r'(?<!perlin)(?<!rand)\)\.slow\((\d+)\)\.s\(', body)

    before = {n: re.search(r'\.scale\("[^"]+"\)\.slow\((\d+)\)', b)
              for n, b in defs.items()}
    for _ in range(10):
        defs = _apply_variants(defs, variants, rng)
        for name, original in before.items():
            if original is None:
                continue
            now = re.search(r'\.scale\("[^"]+"\)\.slow\((\d+)\)', defs[name])
            assert now and now.group(1) == original.group(1), \
                f"{name}: trigger rate moved {original.group(1)} -> {now and now.group(1)}"


def test_modulation_primes_actually_move():
    """The other half of the same rule: drift periods must keep changing, or
    every pass modulates on the same clock."""
    import random
    from utils.audio.performance import _apply_variants

    g = GENRES["ambient"]
    defs = {"turing1": g["lanes"]["turing1"]}
    rng = random.Random(1)
    seen = set()
    for _ in range(10):
        defs = _apply_variants(defs, g["variants"], rng)
        seen.update(re.findall(r"perlin\.range\([^)]*\)\.slow\((\d+)\)", defs["turing1"]))
    assert len(seen) >= 3, f"modulation periods barely move: {seen}"


def test_euclid_gates_are_re_rolled():
    """`euclids` was declared in the variant palette and never applied."""
    import random
    from utils.audio.performance import _apply_variants

    g = GENRES["ambient"]
    defs = {"pings": g["lanes"]["pings"]}
    rng = random.Random(1)
    seen = set()
    for _ in range(12):
        defs = _apply_variants(defs, g["variants"], rng)
        seen.update(re.findall(r'struct\("x(\(\d+,\d+\))"\)', defs["pings"]))
    assert len(seen) >= 3, f"euclid gates never change: {seen}"


def test_set_rewrites_a_head_call_instead_of_appending_a_second_one():
    """A lane's first call carries no leading dot, so SET never found it.

    `SET n` on `n("<0 4>*16").scale(...)` appended a *second* `.n(...)` to the
    end of the chain and still returned True, so nothing reported the failure.
    That is why no genre could ever change its notes: the scripts could edit
    filters, ducking and FM, but not the one thing a listener actually follows.
    """
    lane = Lane("lead", 'n("<0 4 0 9 7>*16").scale("g4:minor").s("supersaw")')
    assert lane.set_param("n", '"<0 3 5 7>*16"') is True
    assert lane.render().count("n(") == 1, "the head call was duplicated"
    assert '<0 3 5 7>*16' in lane.render()
    assert '<0 4 0 9 7>*16' not in lane.render()

    # The same applies to a chord-headed lane.
    pad = Lane("pad", 'chord("<Cm7 Fm7>").voicing().anchor("c4")')
    pad.set_param("chord", '"<Cm7 Ab^7 Fm7 G7>"')
    assert pad.render().count("chord(") == 1
    assert "G7" in pad.render()

    # A chained call must still be rewritten in place, not treated as a head.
    bass = Lane("bass", 'n("0*8").s("supersaw").lpf(400)')
    bass.set_param("lpf", "900")
    assert ".lpf(900)" in bass.render() and ".lpf(400)" not in bass.render()


@pytest.mark.parametrize("genre", genre_names())
def test_every_genre_develops_its_material(genre):
    """Timbre moves alone are not a performance.

    Every script edited filters, delay and distortion constantly, and the notes
    never once changed — so a 5-to-9-minute set replayed a single one-bar
    figure a couple of hundred times. A genre has to move its pitch material at
    least once: the riff, the progression, or (for the generative ones) the
    quantiser or the gate feeding it.
    """
    moves = [m for m in GENRES[genre]["script"] if m["op"] == SET]
    pitch = [m for m in moves
             if m.get("arg") in ("n", "note", "chord", "scale", "mask", "struct")]
    assert pitch, f"{genre} never changes a note across the whole set"


@pytest.mark.parametrize("genre", genre_names())
def test_a_static_root_does_not_sit_under_a_moving_progression(genre):
    """A bass parked on degree 0 under a pad that walks is the defect.

    When the pad reached `-2,2,5` the root still said 0 and the harmony stopped
    functioning. A pulse lane that names a single degree must carry an `.add(n(
    ...))` offset (or name the movement itself) whenever another lane in the
    same genre walks a progression.
    """
    lanes = GENRES[genre]["lanes"]
    walks = any(re.search(r'"<[^"]*,[^"]*\s+-?\d+,', code) for code in lanes.values())
    if not walks:
        return
    for name, code in lanes.items():
        if not re.match(r'n\("<?0>?\*\d+"\)', code):
            continue
        assert ".add(n(" in code, \
            f"{genre}/{name} holds one root while another lane changes chord"

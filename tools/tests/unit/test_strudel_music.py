"""
Tests for the Strudel-backed !music engine that need no browser.

Whether a pattern makes a sound can only be checked by playing it:
tools/maintenance/audition_tracks.py solos every part and measures every
section. The arrangement engine itself is tested in test_music_tracks.py.
"""

import re

import pytest

from utils.audio.performance import Lane


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

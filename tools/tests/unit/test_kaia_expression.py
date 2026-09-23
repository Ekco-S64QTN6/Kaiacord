"""Kaia choosing what to make (art) and how to play it (music)."""
import io
import json
import random

import numpy as np
import pytest

from utils.core import kaia_art_intent as ai
from utils.core.kaia_art import ArtIntent, FractalFlameRenderer, PALETTES, PRIMARY_VARIATIONS


# ── art ──────────────────────────────────────────────────────────────────

def test_words_steer_palette_shape_symmetry_and_complexity():
    it = ai.from_words("a lonely lighthouse in the fog, like a snowflake")
    assert it.palette == "ghost"
    assert it.symmetry == 6
    assert it.complexity == "simple"


def test_her_choice_is_kept_only_where_it_is_on_a_menu():
    it = ai.parse_choice('sure! {"title": "Salt *Light*", "palette": "ember", '
                         '"shapes": ["waves", "laser", "rings"], "symmetry": 7, '
                         '"complexity": "baroque", "feeling": "Homesick"}')
    assert it.title == "salt light"
    assert it.palette == "ember"
    assert it.shapes == ["waves", "rings"]
    assert it.symmetry is None and it.complexity is None
    assert ai.parse_choice("i'd rather not") is None
    assert ai.parse_choice('{"title": "only a title"}') is None


def test_mood_maps_onto_the_same_menus():
    for m in ({"valence": 0.6, "arousal": 0.3, "energy": 0.8},
              {"valence": -0.5, "arousal": 0.2, "energy": 0.1},
              {"valence": 0.1, "arousal": 0.9, "energy": 0.9}):
        it = ai.from_mood(m)
        assert it.palette in PALETTES and it.feeling
        assert all(s in PRIMARY_VARIATIONS for s in it.shapes)


def test_an_image_becomes_a_dark_to_light_palette():
    from PIL import Image
    a = np.zeros((60, 60, 3), np.uint8)
    a[:20] = (60, 20, 90); a[20:40] = (250, 140, 40); a[40:] = (20, 110, 120)
    buf = io.BytesIO(); Image.fromarray(a).save(buf, "PNG")
    lut = ai.palette_from_image(buf.getvalue())
    assert lut.shape == (256, 3)
    lum = lut @ np.array([0.2126, 0.7152, 0.0722])
    assert lum[0] < 0.1 < lum[-1]
    assert ai.palette_from_image(b"not an image") is None


def test_an_unsteered_seed_renders_what_it_always_did():
    """The intent path must not shift the random stream for plain !art --seed N."""
    a = FractalFlameRenderer()._build_system(42, "void")
    r = FractalFlameRenderer(); r.intent = None
    b = r._build_system(42, "void")
    assert a["symmetry_k"] == b["symmetry_k"]
    assert [list(t[1]) for t in a["transforms"]] == [list(t[1]) for t in b["transforms"]]


def test_an_intent_steers_the_system():
    r = FractalFlameRenderer()
    r.intent = ArtIntent(palette="ember", symmetry=6, shapes=["heart"], complexity="intricate")
    sysm = r._build_system(42, None)
    assert (sysm["pal_name"], sysm["symmetry_k"], sysm["n_transforms"]) == ("ember", 6, 4)
    assert sum("heart" in t[1] for t in sysm["transforms"]) >= 2


def test_art_arguments_separate_the_prompt_from_the_flags():
    from utils.commands.art_handler import parse_args
    o = parse_args("!art a storm over the sea --seed 7 --palette void")
    assert (o["prompt"], o["seed"], o["palette"], o["type"]) == ("a storm over the sea", 7, "void", "flame")
    assert parse_args("!art mandelbrot")["type"] == "mandelbrot"


# ── music ────────────────────────────────────────────────────────────────

from utils.audio import dj  # noqa: E402
from utils.audio.performance import build  # noqa: E402
from utils.audio.strudel_patterns import GENRES  # noqa: E402


def _full(genre):
    p = build(GENRES[genre], random.Random(2))
    for lane in p.lanes.values():
        lane.live = True
    return p


def test_she_picks_a_genre_from_mood_and_hour():
    wired = {"valence": 0.5, "arousal": 0.9, "energy": 0.9}
    g, why = dj.pick_genre(wired, 21, GENRES, random.Random(1))
    assert g in ("trance", "psytrance", "drumnbass") and "energy" in why
    g, why = dj.pick_genre(wired, 3, GENRES, random.Random(1))
    assert g in dj._LATE and "late" in why


@pytest.mark.parametrize("genre", sorted(GENRES))
@pytest.mark.parametrize("req", ["darker", "brighter", "faster", "drop", "build", "calmer",
                                 "harder", "more bass", "no drums"])
def test_every_request_edits_every_genre_cleanly(genre, req):
    p = _full(genre)
    if req in ("build", "harder", "more bass"):
        for n in list(p.lanes)[: len(p.lanes) // 2]:
            p.lanes[n].live = False
    before = p.code()
    r = dj.apply_request(req, p, GENRES[genre]["cpm"], random.Random(0))
    assert r.understood
    after = p.code()
    if r.changed:
        assert after != before
    assert after.count("(") == after.count(")")


def test_tempo_requests_stay_within_a_fifth_of_the_genre():
    p = _full("house")
    for _ in range(20):
        dj.apply_request("faster", p, GENRES["house"]["cpm"])
    assert dj.bpm_of(p.cpm) <= 124 * 1.2 + 0.1


def test_a_drop_brings_the_drums_back_later():
    p = _full("techno")
    r = dj.apply_request("drop", p, GENRES["techno"]["cpm"])
    assert r.restore_after_s and "kick" in r.restore_lanes and not p.lanes["kick"].live


def test_an_unknown_request_is_not_understood():
    assert not dj.apply_request("play something weird", _full("dub"), GENRES["dub"]["cpm"]).understood


def test_music_arguments_route_requests():
    from utils.commands.music_handler import _parse
    assert _parse("!music darker".split()) == ("request", None, "darker")
    assert _parse("!music more bass".split()) == ("request", None, "more bass")
    assert _parse("!music on --house".split())[:2] == ("on", "house")
    assert _parse("!music".split())[0] == "status"


# ── memory ───────────────────────────────────────────────────────────────

def test_what_she_makes_reaches_her_history_and_growth_log(tmp_path, monkeypatch):
    from collections import deque
    from utils.core import kaia_expression
    from utils.infrastructure.system import bot_state as bs
    log = tmp_path / "growth.jsonl"
    monkeypatch.setattr(kaia_expression, "telemetry_path", lambda p: str(log))
    monkeypatch.setattr(bs.bot_state, "channel_memory", {7: deque(maxlen=10)})
    kaia_expression.remember("art", '[i made a piece called "salt light".]', channel_id=7, title="salt light")
    assert bs.bot_state.channel_memory[7][-1]["content"] == '[i made a piece called "salt light".]'
    event = json.loads(log.read_text().splitlines()[-1])
    assert (event["type"], event["kind"], event["title"]) == ("creation", "art", "salt light")

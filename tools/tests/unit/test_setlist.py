"""Sets prefer partners that blend long.

31% of locking pairs lock only for 16 beats (~7.5 s at 128 bpm), and nothing
preferred the long ones: on 31 Oct a third of the hour sets' transitions were
16-beat blends, which Ekco heard as "mixes into the next song super quick".
"""
import random
from types import SimpleNamespace

import pytest

from utils.audio import mixcheck, setlist
from utils.audio.library import Record

N = 14


def _graph(key_b="8A"):
    """Two chains, A and B. Each record blends 64 beats into the next of its
    own chain and 16 beats into the next of the other."""
    recs, edges = {}, {}
    for chain, key in (("A", "8A"), ("B", key_b)):
        for i in range(N):
            recs[f"/m/{chain}{i}.mp3"] = Record(f"/m/{chain}{i}.mp3", chain, f"{chain}{i}", 124.0, key, "house")
    for i in range(N - 1):
        for own, other in (("A", "B"), ("B", "A")):
            edges[f"/m/{own}{i}.mp3"] = {
                f"/m/{own}{i + 1}.mp3": {"beats": 64, "back": 0, "cue": 0, "agree": 16},
                f"/m/{other}{i + 1}.mp3": {"beats": 16, "back": 0, "cue": 0, "agree": 4},
            }
    g = {"records": {p: {"seconds": 420.0} for p in recs}, "edges": edges}
    return g, recs


def _transitions(g, sets):
    return [g["edges"][a][b]["beats"] for st in sets for a, b in zip(st, st[1:])]


def test_sets_take_the_partner_that_blends_long():
    g, live = _graph()
    sets = setlist.make_sets(g, live, random.Random(1))
    assert sets
    assert 16 not in _transitions(g, sets)


def test_without_the_preference_short_blends_get_in(monkeypatch):
    """The test above would pass vacuously if the walk never met a 16-beat edge."""
    monkeypatch.setattr(setlist, "blend_rank", lambda edge: 0)
    g, live = _graph()
    assert 16 in _transitions(g, setlist.make_sets(g, live, random.Random(1)))


def test_blend_length_does_not_outweigh_a_bad_key_by_itself():
    assert setlist.blend_rank({"beats": 64}) < setlist.blend_rank({"beats": 32}) < setlist.blend_rank({"beats": 16})
    # 32 beats in key (1 + 0) beats 64 beats two steps away (0 + 1)? No — equal
    # rank, so key compatibility is never sacrificed for a shorter difference.
    assert setlist.blend_rank({"beats": 32}) + 0 <= setlist.blend_rank({"beats": 64}) + 1
    assert setlist.blend_rank({}) == setlist.blend_rank({"beats": 16})


def test_set_builder_widens_beyond_five_dead_ends_to_find_a_full_set():
    """The sixth-ranked edge is the only route to a set above SET_MIN_S."""
    live = {}

    def add(name):
        path = f"/m/{name}.mp3"
        rec = Record(path, f"Artist {name}", name, 124.0, "8A", "house")
        live[path] = rec
        return rec

    start = add("Start")
    dead_ends = [add(f"Dead{i}") for i in range(5)]
    viable = [add(f"Viable{i}") for i in range(8)]

    long_edge = {"beats": 64, "back": 0, "cue": 0, "agree": 16}
    short_edge = {"beats": 16, "back": 0, "cue": 0, "agree": 4}
    edges = {start.path: {r.path: dict(long_edge) for r in dead_ends}}
    # This valid route ranks sixth because its first measured blend is shorter.
    edges[start.path][viable[0].path] = dict(short_edge)
    for a, b in zip(viable, viable[1:]):
        edges[a.path] = {b.path: dict(long_edge)}

    graph = {
        "records": {path: {"seconds": 500.0} for path in live},
        "edges": edges,
    }
    sets = setlist.make_sets(graph, live, random.Random(1))

    assert sets
    assert sets[0][0] == start.path
    assert viable[0].path in sets[0]
    assert len(sets[0]) >= 7


def test_selection_rank_prefers_exact_style_before_family_neighbours():
    current = Record("/m/current.mp3", "Alpha", "Current", 124.0, "8A", "House")
    exact = Record("/m/exact.mp3", "Beta", "Exact", 124.0, "8A", "House")
    disco = Record("/m/disco.mp3", "Gamma", "Disco", 124.0, "8A", "Disco")
    techno = Record("/m/techno.mp3", "Delta", "Techno", 124.0, "8A", "Techno")
    edge = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}

    exact_rank = setlist.transition_rank(current, exact, edge, history=[current])
    disco_rank = setlist.transition_rank(current, disco, edge, history=[current])
    techno_rank = setlist.transition_rank(current, techno, edge, history=[current])
    assert exact_rank < disco_rank < techno_rank


def test_selection_rank_softly_prefers_artist_variety():
    current = Record("/m/current.mp3", "Alpha", "Current", 124.0, "8A", "House")
    fresh = Record("/m/fresh.mp3", "Beta", "Fresh", 124.0, "8A", "House")
    repeat = Record("/m/repeat.mp3", "Alpha", "Repeat", 124.0, "8A", "House")
    edge = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}

    assert setlist.transition_rank(current, fresh, edge, history=[current]) < setlist.transition_rank(
        current, repeat, edge, history=[current]
    )
    # It remains a preference, not an exclusion from the graph.
    assert setlist.transition_rank(current, repeat, edge, history=[current])


def test_selection_rank_uses_agreement_fraction_not_raw_count():
    current = Record("/m/current.mp3", "Alpha", "Current", 124.0, "8A", "House")
    wide_low_confidence = {"beats": 128, "agree": 20, "bars": 32, "ratio": 1.0}
    shorter_high_confidence = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}
    candidate = Record("/m/candidate.mp3", "Beta", "Candidate", 124.0, "8A", "House")

    assert setlist.blend_rank(wide_low_confidence) == setlist.blend_rank(shorter_high_confidence)
    assert setlist.transition_rank(current, candidate, shorter_high_confidence) < setlist.transition_rank(
        current, candidate, wide_low_confidence
    )


def test_selection_rank_keeps_the_existing_key_and_blend_tradeoff():
    current = Record("/m/current.mp3", "Alpha", "Current", 124.0, "8A", "House")
    same_key = Record("/m/same-key.mp3", "Beta", "Same key", 124.0, "8A", "House")
    two_steps = Record("/m/two-steps.mp3", "Gamma", "Two steps", 124.0, "10A", "House")
    short = {"beats": 32, "agree": 8, "bars": 8, "ratio": 1.0}
    long = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}

    assert setlist.transition_rank(current, same_key, short) < setlist.transition_rank(current, two_steps, long)


def test_artist_matching_ignores_compilation_placeholders():
    from utils.audio import library
    various = Record("/m/various.mp3", "Various Artists", "Compilation", 124.0, "8A", "House")
    named = Record("/m/named.mp3", "Beta", "Named", 124.0, "8A", "House")
    assert not library.shares_artist(various, named)


def test_set_method_upgrade_rebuilds_sets_without_invalidating_audio_edges():
    graph = {
        "method": setlist.METHOD,
        "sets_method": setlist.SET_METHOD - 1,
        "records": {},
        "edges": {},
        "checked": {},
    }
    assert setlist.needs_build(graph, [])
    assert setlist.pending(graph, []) == {"records": 0, "pairs": 0}
    graph["sets_method"] = setlist.SET_METHOD
    assert not setlist.needs_build(graph, [])


def test_peeking_a_set_does_not_consume_rotation(tmp_path, monkeypatch):
    from utils.audio.library import Record

    path = tmp_path / "set_rotation.json"
    monkeypatch.setattr(setlist, "_rotation_path", lambda: path)
    crate = [
        Record(f"/m/{i}.mp3", "Artist", f"Track {i}", 124.0, "8A", "House")
        for i in range(8)
    ]
    graph = {"sets": [
        [r.path for r in crate[:4]],
        [r.path for r in crate[4:]],
    ]}

    first = setlist.peek_next_set(graph, crate)
    assert first == [r.path for r in crate[:4]]
    assert setlist.peek_next_set(graph, crate) == first
    assert not path.exists(), "peeking must not write/advance rotation"

    assert setlist.advance_rotation(graph, crate) is True
    assert setlist.peek_next_set(graph, crate) == [r.path for r in crate[4:]]
    assert setlist.advance_rotation(graph, crate) is True
    assert setlist.peek_next_set(graph, crate) == first


def test_legacy_next_set_still_selects_and_advances(tmp_path, monkeypatch):
    from utils.audio.library import Record

    path = tmp_path / "set_rotation.json"
    monkeypatch.setattr(setlist, "_rotation_path", lambda: path)
    crate = [
        Record(f"/m/{i}.mp3", "Artist", f"Track {i}", 124.0, "8A", "House")
        for i in range(8)
    ]
    graph = {"sets": [
        [r.path for r in crate[:4]],
        [r.path for r in crate[4:]],
    ]}
    assert setlist.next_set(graph, crate) == [r.path for r in crate[:4]]
    assert setlist.peek_next_set(graph, crate) == [r.path for r in crate[4:]]


def test_set_builder_prefers_a_coherent_handoff_over_a_cluttered_measured_pair():
    from utils.audio.songmap import PhraseProfile, PhraseState

    def rec(name, genre="House"):
        return Record(f"/m/{name}.mp3", f"Artist {name}", name, 120.0, "8A", genre)

    def profile(section, *, level=-12.0):
        state = PhraseState(
            start=0.0, end=64.0, aligned=True, bars=4,
            full_db=level, bass_db=level, lead_db=level,
            upper_db=level, transient_db=level, energy_change_db=0.0,
            section=section, section_strength=0.8,
        )
        return PhraseProfile(64.0, 4, 120.0, 8.0, True, (state,))

    start, crowded, coherent = rec("Start"), rec("Crowded"), rec("Surprise", "Techno")
    c1, c2, s1, s2 = rec("C1"), rec("C2"), rec("S1"), rec("S2")
    live = {r.path: r for r in (start, crowded, coherent, c1, c2, s1, s2)}
    edge = {"beats": 64, "back": 0, "cue": 0, "agree": 16, "bars": 16, "ratio": 1.0}
    graph = {
        "records": {},
        "edges": {
            start.path: {crowded.path: dict(edge), coherent.path: dict(edge)},
            crowded.path: {c1.path: dict(edge)},
            c1.path: {c2.path: dict(edge)},
            coherent.path: {s1.path: dict(edge)},
            s1.path: {s2.path: dict(edge)},
        },
    }
    profiles = {
        start.path: profile("build_candidate", level=-2.0),
        crowded.path: profile("drop_candidate", level=-2.0),
        coherent.path: profile("drop_candidate", level=-18.0),
    }

    sets = setlist.make_sets(graph, live, random.Random(7), profiles=profiles)

    assert sets and sets[0][0] == start.path
    assert sets[0][1] == coherent.path
    chosen = graph["set_plans"][0]["transitions"][0]
    assert chosen["technical"]["measured_lock"] is True
    assert chosen["technical"]["beats"] == 64
    assert chosen["musical"]["preference"] == "prefer"
    assert chosen["musical"]["incoming_section"] == "drop_candidate"
    assert chosen["arc"]["contextual_preference"] > 0


def test_set_builder_keeps_technical_lock_and_musical_score_separate_without_profiles():
    records = [Record(f"/m/{i}.mp3", "Artist", f"Track {i}", 120.0, "8A", "House") for i in range(4)]
    edge = {"beats": 64, "agree": 16, "bars": 16, "ratio": 1.0}
    graph = {
        "records": {},
        "edges": {
            records[0].path: {records[1].path: dict(edge), records[2].path: dict(edge)},
            records[1].path: {records[2].path: dict(edge)},
            records[2].path: {records[3].path: dict(edge)},
        },
    }
    live = {r.path: r for r in records}
    sets = setlist.make_sets(graph, live, random.Random(2))

    assert sets
    first = graph["set_plans"][0]["transitions"][0]
    assert first["technical"]["measured_lock"] is True
    assert first["musical"]["available"] is False
    assert first["musical"]["score"] == 0.0



def test_verify_converts_pitch_rated_source_clock_plan_to_wall_time(monkeypatch):
    plan = SimpleNamespace(
        playback_rate=1.06,
        start=10.6,
        drop=18.02,
        length=8.48,
        offset=0.25,
        ratio=1.04,
        beat=0.53,
        done=26.5,
    )
    observed = {}

    def check(out_path, out_ratio, in_path, in_ratio, start, offset, drop, heard, beat):
        observed.update(
            out_path=out_path,
            out_ratio=out_ratio,
            in_path=in_path,
            in_ratio=in_ratio,
            start=start,
            offset=offset,
            drop=drop,
            heard=heard,
            beat=beat,
        )
        return SimpleNamespace(locked=True, correction_ms=None)

    monkeypatch.setattr(mixcheck, "check", check)
    verdict, shift = setlist.verify("out.wav", 1.06, "in.wav", plan)

    assert verdict.locked
    assert shift == 0.0
    assert observed["out_path"] == "out.wav"
    assert observed["out_ratio"] == pytest.approx(1.06)
    assert observed["in_path"] == "in.wav"
    assert observed["in_ratio"] == pytest.approx(1.04)
    assert observed["start"] == pytest.approx(10.0)
    assert observed["offset"] == 0.25
    assert observed["drop"] == pytest.approx(17.0)
    assert observed["heard"] == pytest.approx(8.0)
    assert observed["beat"] == pytest.approx(0.5)

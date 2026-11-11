"""Sets prefer partners that blend long.

31% of locking pairs lock only for 16 beats (~7.5 s at 128 bpm), and nothing
preferred the long ones: on 31 Oct a third of the hour sets' transitions were
16-beat blends, which Ekco heard as "mixes into the next song super quick".
"""
import random

from utils.audio import setlist
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



def test_selection_rank_prefers_exact_style_before_family_neighbours():
    current = Record("/m/current.mp3", "First Artist", "Current", 124.0, "8A", "House")
    exact = Record("/m/exact.mp3", "Second Artist", "Exact", 124.0, "8A", "House")
    disco = Record("/m/disco.mp3", "Third Artist", "Disco", 124.0, "8A", "Disco")
    techno = Record("/m/techno.mp3", "Fourth Artist", "Techno", 124.0, "8A", "Techno")
    edge = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}

    exact_rank = setlist.transition_rank(current, exact, edge, history=[current])
    disco_rank = setlist.transition_rank(current, disco, edge, history=[current])
    techno_rank = setlist.transition_rank(current, techno, edge, history=[current])
    assert exact_rank < disco_rank < techno_rank


def test_selection_rank_softly_prefers_artist_variety():
    current = Record("/m/current.mp3", "First Artist", "Current", 124.0, "8A", "House")
    fresh = Record("/m/fresh.mp3", "Second Artist", "Fresh", 124.0, "8A", "House")
    repeat = Record("/m/repeat.mp3", "First Artist", "Repeat", 124.0, "8A", "House")
    edge = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}

    assert setlist.transition_rank(current, fresh, edge, history=[current]) < setlist.transition_rank(
        current, repeat, edge, history=[current]
    )
    # It remains a preference, not an exclusion from the graph.
    assert setlist.transition_rank(current, repeat, edge, history=[current])


def test_selection_rank_uses_agreement_fraction_not_raw_count():
    current = Record("/m/current.mp3", "First Artist", "Current", 124.0, "8A", "House")
    wide_low_confidence = {"beats": 128, "agree": 20, "bars": 32, "ratio": 1.0}
    shorter_high_confidence = {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0}
    candidate = Record("/m/candidate.mp3", "Second Artist", "Candidate", 124.0, "8A", "House")

    assert setlist.blend_rank(wide_low_confidence) == setlist.blend_rank(shorter_high_confidence)
    assert setlist.transition_rank(current, candidate, shorter_high_confidence) < setlist.transition_rank(
        current, candidate, wide_low_confidence
    )


def test_set_method_upgrade_rebuilds_sets_without_invalidating_audio_edges():
    graph = {"method": setlist.METHOD, "sets_method": setlist.SET_METHOD - 1,
             "records": {}, "edges": {}, "checked": {}}
    assert setlist.needs_build(graph, [])
    assert setlist.pending(graph, []) == {"records": 0, "pairs": 0}
    graph["sets_method"] = setlist.SET_METHOD
    assert not setlist.needs_build(graph, [])

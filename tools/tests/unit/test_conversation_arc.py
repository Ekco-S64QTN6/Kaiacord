"""Minute forty used to read like minute one. The arc says where a
conversation is — and never guesses that it is winding down."""
import pytest

from utils.core import conversation_arc as arc

NOW = 1_000_000.0


def _turns(*ages_s):
    return [{"role": "user", "content": "x", "timestamp": NOW - a} for a in ages_s]


@pytest.mark.parametrize("text,bye", [
    ("good night kaia!", True), ("gn", True), ("Very funny. Until later Kaia.", True),
    ("later we can talk more", False), ("night shift was rough", False),
    ("YouTube thinks I need stories when I'm going to bed", False), ("ok", False),
])
def test_only_an_explicit_goodbye_closes(text, bye):
    assert arc.is_signoff(text) is bye


def test_a_quiet_channel_is_a_fresh_start():
    assert "fresh start" in arc.note_for(_turns(5 * 3600), "hey kaia", NOW)


def test_a_long_run_of_messages_is_well_along():
    turns = _turns(*range(50 * 60, 0, -3 * 60))          # every 3 min for 50 min
    note = arc.note_for(turns, "what do you think", NOW)
    assert "going for 50 minutes" in note


def test_short_replies_and_pauses_never_read_as_winding_down():
    turns = _turns(20 * 60, 10 * 60, 5 * 60)
    assert arc.note_for(turns, "ok", NOW) == ""
    assert arc.note_for(turns, "hm", NOW) == ""


def test_a_run_breaks_at_a_long_pause():
    turns = _turns(3 * 3600, *range(30 * 60, 0, -2 * 60))  # old, then 30 min of chat
    assert arc.note_for(turns, "and then?", NOW) == ""

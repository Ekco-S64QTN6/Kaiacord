"""Kaia's feed in the booth: lines built from what the mixer actually did."""
import types

from utils.audio import dj_voice, library


def rec(title, key="8A", bpm=124.0):
    return library.Record(path=f"/m/{title}.mp3", artist="Artist", title=title, bpm=bpm, key=key, genre="House")


def test_a_pick_says_what_was_measured_and_the_key_move():
    line = dj_voice.chose_next(rec("one", "8A"), rec("two", "9A"), {"agree": 14, "bars": 16}, True)
    assert "two" in line and ("14" in line and "16" in line) and "8A" in line and "9A" in line


def test_a_pick_with_no_partner_says_it_will_echo_out():
    for _ in range(10):
        line = dj_voice.chose_next(rec("one"), rec("two"), None, False)
        assert "echo" in line and "cut" not in line


def test_a_nudged_blend_says_which_way():
    plan = types.SimpleNamespace(kind="blend", length=32.0, beat=0.5, check="locked: x; moved -54 ms", fallback="")
    line = dj_voice.planned(plan, "two")
    assert "16" in line and "54 ms earlier" in line and "-54" not in line


def test_an_unlocked_plan_says_it_echoes_out_and_why():
    plan = types.SimpleNamespace(kind="echo", length=0.06, beat=0.5, check="NOT locked", fallback="unlocked")
    for _ in range(10):
        line = dj_voice.planned(plan, "two")
        assert "two" in line and "echo" in line and ("pulse" in line or "lock" in line)


def test_a_swapped_pick_names_both_records():
    for _ in range(10):
        line = dj_voice.swapped("one", "two")
        assert "one" in line and "two" in line


def test_the_session_feed_records_what_plays():
    from utils.audio import records as R
    vc = types.SimpleNamespace(guild=types.SimpleNamespace(id=1), channel=types.SimpleNamespace(name="General", members=[]))
    s = R.RecordsSession(vc, [], "Ekco")
    one = rec("one")
    s.set_list = [one.path, rec("two").path]
    s._changed(one)
    assert s.chatter and s.chatter[-1]["kind"] == "now" and "one" in s.chatter[-1]["text"]
    assert "1 of 2" in s.chatter[-1]["text"] or "track 1 of 2" in s.chatter[-1]["text"] or "1 left" in s.chatter[-1]["text"]

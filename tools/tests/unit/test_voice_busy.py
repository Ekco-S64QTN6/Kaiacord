"""Background work waits while Kaia is playing in voice.

A records set ran into the dream cycle on 5 Oct: the dream's indexing and
persists held the GIL and the voice thread came back 60–170 ms late fifteen
times in five minutes. Dreams, curation, the evening reflection and the RAG
sweep now wait for the music to stop.
"""
import asyncio
import types

import pytest

from utils.audio import voice_busy


@pytest.fixture
def records_playing(monkeypatch):
    from utils.audio import records
    s = types.SimpleNamespace(_closing=False, channel_name="General")
    monkeypatch.setitem(records._sessions, 99, s)
    return s


def test_nothing_playing_is_quiet():
    assert voice_busy.playing() == ""


def test_a_records_set_is_playing(records_playing):
    assert voice_busy.playing() == "records in General"
    records_playing._closing = True
    assert voice_busy.playing() == ""


def test_the_wait_returns_when_the_music_stops(records_playing):
    async def run():
        async def stop_soon():
            await asyncio.sleep(0.05)
            records_playing._closing = True
        asyncio.get_running_loop().create_task(stop_soon())
        return await voice_busy.wait_until_quiet("Dream cycle", max_wait_s=5, poll_s=0.02)
    assert asyncio.run(run()) is True


def test_the_wait_gives_up_after_its_cap(records_playing):
    assert asyncio.run(voice_busy.wait_until_quiet("Dream cycle", max_wait_s=0.06, poll_s=0.02)) is False


def test_the_rag_sweep_waits_and_keeps_its_trigger(records_playing, monkeypatch, tmp_path):
    from utils.core import rag_utils
    from utils.infrastructure.system import maintenance_tasks as mt
    trigger = tmp_path / ".trigger_reindex"
    trigger.write_text("")
    monkeypatch.setattr(rag_utils, "reindex_trigger_path", lambda: trigger)
    called = []
    rag = types.SimpleNamespace(_initialized=True, refresh_knowledge_base=lambda: called.append(1),
                                persist_needed=False)
    monkeypatch.setattr(mt, "ctx", types.SimpleNamespace(rag=rag))
    asyncio.run(mt.rag_maintenance_task.coro())
    assert trigger.exists() and not called


def test_every_deferring_task_asks_first():
    import inspect
    from utils.core import background_tasks as bt
    src = inspect.getsource(bt)
    for what in ("Dream cycle", "Dream curation", "Evening reflection", "Metadata enrichment", "Corpus audit"):
        assert f'wait_until_quiet("{what}"' in src


def test_the_nightly_sweep_pauses_for_records_but_not_a_tuned_channel(records_playing, monkeypatch):
    from utils.radio import scanner
    stopped = []
    monkeypatch.setattr(scanner, "_running", True)
    monkeypatch.setattr(scanner, "_pinned", None)
    monkeypatch.setattr(scanner, "_paused_for", "")
    monkeypatch.setattr(scanner, "_stop_all", lambda: stopped.append(1))
    for f in ("tuned", "asked", "due_net"):
        monkeypatch.setattr(scanner, f, lambda *a: None)
    monkeypatch.setattr(scanner, "listening_along", lambda: False)
    assert scanner.tick() is False and stopped and scanner._paused_for == "records in General"
    stopped.clear()
    monkeypatch.setattr(scanner, "tuned", lambda *a: {"freq_hz": 146520000})
    scanner.tick()
    assert not stopped                                     # a channel tuned on purpose keeps playing


def test_no_new_shortwave_listen_starts_during_records(records_playing, monkeypatch):
    from utils.radio import watch, priyom
    monkeypatch.setattr(priyom, "upcoming", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked")))
    asyncio.run(watch.tick())                              # returns before reading the schedule


def test_a_profile_is_rewritten_when_it_is_old_and_there_is_enough_new_talk(tmp_path):
    """Measured by the date in each log's name, not mtimes (enrichment bumps
    those every night); 7 days and 15 KB, or 3 days and 100 KB."""
    import os, time
    from utils.core.kaia_dream import profile_stale
    d = tmp_path / "Ekco_1"
    d.mkdir()
    prof = d / "user_profile.md"
    prof.write_text("profile")
    day = lambda n: time.strftime("%Y%m%d", time.localtime(time.time() - n * 86400))
    def log(n, kb):
        f = d / f"interactions_{day(n)}.md"
        f.write_text("x" * kb * 1024)
        return f
    def age(days):
        t = time.time() - days * 86400
        os.utime(prof, (t, t))
    old = log(30, 200)                      # before the profile: never "new", however recently touched
    os.utime(old, None)
    logs = [old, log(1, 20)]
    age(2)
    assert profile_stale(prof, logs)[0] is False           # 20 KB new but only 2 days old
    age(8)
    assert profile_stale(prof, logs)[0] is True            # a week old with 20 KB of new talk
    logs = [old, log(0, 120)]
    age(4)
    assert profile_stale(prof, logs)[0] is True            # a busy few days
    age(1)
    assert profile_stale(prof, logs)[0] is False


def test_the_profile_writer_does_not_shadow_its_own_import():
    """A second `from … import write_atomic` inside one branch made the name
    local to the whole function; every ordinary profile write raised from
    27 Sept and the error only reached stdout."""
    import ast, inspect
    from tools.maintenance import generate_user_profiles as g
    tree = ast.parse(inspect.getsource(g.generate_profile))
    local = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and any(a.name == "write_atomic" for a in n.names)]
    assert not local

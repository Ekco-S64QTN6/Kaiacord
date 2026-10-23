"""The list of mentions she has answered survives a snapshot, and a test run
never writes the live one."""
import asyncio

from utils.social.social_tracker import SocialTracker


def test_a_snapshot_keeps_every_reply_and_drops_the_log(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", "")
    t = SocialTracker(log_path=str(tmp_path / "replied.log"), state_path=str(tmp_path / "state.json"))
    asyncio.run(t.mark_replied("bsky:1", "bluesky", "root", "a"))
    asyncio.run(t.mark_replied("bsky:2", "bluesky", "root", "a"))
    asyncio.run(t.save_snapshot())
    assert not (tmp_path / "replied.log").exists()
    again = SocialTracker(log_path=str(tmp_path / "replied.log"), state_path=str(tmp_path / "state.json"))
    assert again.is_replied("bsky:1") and again.is_replied("bsky:2")
    assert again.get_thread_count("root", "a") == 2


def test_the_singleton_does_not_point_at_live_memory_under_pytest():
    from utils.social.social_tracker import social_tracker
    assert ".test" in social_tracker.state_path.name and ".test" in social_tracker.log_path.name


def test_two_stale_tracker_instances_merge_ids_and_thread_counts(tmp_path, monkeypatch):
    """One process's snapshot must not erase events from another's append log."""
    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", "")
    log_path = str(tmp_path / "shared.log")
    state_path = str(tmp_path / "shared.json")
    a = SocialTracker(log_path=log_path, state_path=state_path)
    b = SocialTracker(log_path=log_path, state_path=state_path)

    async def run():
        await a.mark_replied("x:one", "x", "root", "person")
        await b.mark_replied("bsky:two", "bluesky", "root", "person")
        await a.save_snapshot()
        # b's memory was stale when it was constructed; its save must merge,
        # not replace the two-event disk snapshot with its one local event.
        await b.save_snapshot()

    asyncio.run(run())
    loaded = SocialTracker(log_path=log_path, state_path=state_path)
    assert loaded.is_replied("x:one")
    assert loaded.is_replied("bsky:two")
    assert loaded.get_thread_count("root", "person") == 2
    assert not (tmp_path / "shared.log").exists()


def _social_tracker_process_worker(log_path, state_path, barrier, mention_id):
    import asyncio
    from utils.social.social_tracker import SocialTracker

    tracker = SocialTracker(log_path=log_path, state_path=state_path)
    barrier.wait(timeout=10)  # both processes hold an initially stale snapshot
    asyncio.run(tracker.mark_replied(mention_id, "test", "shared-root", "shared-user"))
    barrier.wait(timeout=10)  # both appends are complete before either compacts
    asyncio.run(tracker.save_snapshot())


def test_separate_processes_do_not_drop_events_during_compaction(tmp_path, monkeypatch):
    import multiprocessing

    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", "")
    log_path = str(tmp_path / "mp.log")
    state_path = str(tmp_path / "mp.json")
    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(2)
    processes = [
        ctx.Process(target=_social_tracker_process_worker,
                    args=(log_path, state_path, barrier, "x:process-a")),
        ctx.Process(target=_social_tracker_process_worker,
                    args=(log_path, state_path, barrier, "bsky:process-b")),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert not process.is_alive(), "social tracker process hung under file locking"
        assert process.exitcode == 0

    loaded = SocialTracker(log_path=log_path, state_path=state_path)
    assert loaded.is_replied("x:process-a")
    assert loaded.is_replied("bsky:process-b")
    assert loaded.get_thread_count("shared-root", "shared-user") == 2


def test_stale_full_deque_cannot_evict_newer_snapshot_ids_at_retention_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", "")
    log_path = str(tmp_path / "bounded.log")
    state_path = str(tmp_path / "bounded.json")
    seed = SocialTracker(log_path=log_path, state_path=state_path, max_ids=2)

    async def seed_old_history():
        await seed.mark_replied("x:old-1", "x", "root", "person")
        await seed.mark_replied("x:old-2", "x", "root", "person")
        await seed.save_snapshot()

    asyncio.run(seed_old_history())
    a = SocialTracker(log_path=log_path, state_path=state_path, max_ids=2)
    b = SocialTracker(log_path=log_path, state_path=state_path, max_ids=2)

    async def race_stale_snapshot():
        await a.mark_replied("x:new-a", "x", "root", "person")
        await b.mark_replied("bsky:new-b", "bluesky", "root", "person")
        await a.save_snapshot()
        await b.save_snapshot()

    asyncio.run(race_stale_snapshot())
    loaded = SocialTracker(log_path=log_path, state_path=state_path, max_ids=2)
    assert loaded.get_all_replied_ids() == {"x:new-a", "bsky:new-b"}
    assert loaded.get_thread_count("root", "person") == 4


def test_old_generation_log_residue_does_not_resurrect_retired_ids(tmp_path, monkeypatch):
    """A crash after state replacement must not bypass the retention cap."""
    import json

    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", "")
    log_path = tmp_path / "generation.log"
    state_path = tmp_path / "generation.json"
    state_path.write_text(json.dumps({
        "replied_ids": ["x:new-a", "x:new-b"],
        "thread_counts": {"root": {"person": 2}},
        "log_generation": 4,
    }))
    # This event was already represented by a prior snapshot, then evicted.
    # Its old-generation JSONL line remains only because the process crashed
    # before unlinking the compacted log.
    log_path.write_text(
        json.dumps({
            "mention_id": "x:retired",
            "platform": "x",
            "root_uri": "root",
            "user_handle": "person",
            "generation": 3,
            "timestamp": 1,
        }) + "\n"
    )
    tracker = SocialTracker(
        log_path=str(log_path), state_path=str(state_path), max_ids=2
    )
    assert tracker.get_all_replied_ids() == {"x:new-a", "x:new-b"}

    # Also simulate a long-lived process refreshing after another process has
    # advanced the snapshot and left the same crash residue behind.
    (tmp_path / "generation2.json").write_text(json.dumps({
        "replied_ids": ["x:latest-a", "x:latest-b"],
        "thread_counts": {"root": {"person": 3}},
        "log_generation": 5,
    }))
    tracker.state_path = tmp_path / "generation2.json"
    tracker._refresh_from_disk_sync()
    assert tracker.get_all_replied_ids() == {"x:latest-a", "x:latest-b"}
    assert not tracker.is_replied("x:retired")

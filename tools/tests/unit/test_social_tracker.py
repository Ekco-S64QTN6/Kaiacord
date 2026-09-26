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

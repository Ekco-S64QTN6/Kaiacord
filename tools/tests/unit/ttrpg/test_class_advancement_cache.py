"""The wealthiest-title background refresh is single-flight and publishes atomically."""
import json

from utils.ttrpg import class_advancement as ca


def test_stale_wealthiest_cache_schedules_only_one_refresh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "memory" / "ttrpg" / "characters"
    directory.mkdir(parents=True)
    (directory / "42.json").write_text(json.dumps({
        "user_id": "42", "gil": 1200, "bank_balance": 500,
    }), encoding="utf-8")

    monkeypatch.setattr(ca, "_WEALTHIEST_CACHE", {
        "timestamp": 0, "uid": None, "updating": False,
    })
    started = []

    class PausedThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon
            started.append(self)

        def start(self):
            # Keep the refresh in-flight so later cache misses race with the
            # updating flag without touching the real filesystem on a thread.
            pass

    monkeypatch.setattr(ca.threading, "Thread", PausedThread)

    for uid in range(20):
        ca._is_wealthiest({"user_id": str(uid)})

    assert len(started) == 1
    assert ca._WEALTHIEST_CACHE["updating"] is True


def test_wealthiest_refresh_publishes_uid_timestamp_and_flag_consistently(
    tmp_path, monkeypatch
):
    import os
    import time

    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "memory" / "ttrpg" / "characters"
    directory.mkdir(parents=True)
    (directory / "42.json").write_text(json.dumps({
        "user_id": "42", "gil": 1200, "bank_balance": 500,
    }), encoding="utf-8")
    monkeypatch.setattr(ca, "_WEALTHIEST_CACHE", {
        "timestamp": 0, "uid": None, "updating": False,
    })

    class InlineThread:
        def __init__(self, target, daemon=False):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(ca.threading, "Thread", InlineThread)

    assert ca._is_wealthiest({"user_id": "42"}) is False  # stale snapshot on refresh call
    assert ca._WEALTHIEST_CACHE["uid"] == "42"
    assert ca._WEALTHIEST_CACHE["timestamp"] > 0
    assert ca._WEALTHIEST_CACHE["updating"] is False
    assert ca._is_wealthiest({"user_id": "42"}) is True

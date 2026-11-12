"""Bounded, lock-serialized channel history and retrieval lifecycle."""
import json
import threading
import time

from utils.infrastructure.system.bot_state import BotState


def test_external_channel_activity_is_persisted_and_restored(tmp_path):
    path = tmp_path / "bot_state.json"
    state = BotState(state_file=str(path))
    channel_id = 9_876_543_210  # synthetic external-conversation key
    stamp = time.time() - 30
    try:
        assert state.replace_channel_memory(channel_id, [
            {"role": "user", "content": "a forum turn", "timestamp": stamp, "external": "forum"}
        ])
        state.save()
    finally:
        state.close()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["channel_memory_activity"][str(channel_id)] == stamp
    restored = BotState(state_file=str(path))
    try:
        assert restored.channel_memory_activity[channel_id] == stamp
        assert restored.channel_memory_snapshot(channel_id)[0]["content"] == "a forum turn"
    finally:
        restored.close()


def test_high_cardinality_prune_bounds_inactive_channels_and_keeps_active_dm_and_channel(tmp_path):
    state = BotState(state_file=str(tmp_path / "state.json"))
    now = time.time()
    state.max_memory_channels = 12
    state.memory_channel_retention_s = 90 * 86400
    state.memory_channel_active_grace_s = 3600
    try:
        for channel_id in range(1000, 1040):
            state.replace_channel_memory(channel_id, [
                {"role": "user", "content": f"old-{channel_id}", "timestamp": now - 7200}
            ])
        state.append_channel_turn(42, {"role": "user", "content": "active channel", "timestamp": now})
        state.append_channel_turn(77, {"role": "user", "content": "active DM", "timestamp": now})
        evicted = state.prune_channel_memory(now=now)
        held = state.channel_memory_snapshot(42) + state.channel_memory_snapshot(77)
        assert len(state.channel_memory) <= 12
        assert 42 in state.channel_memory and 77 in state.channel_memory
        assert any(t["content"] == "active channel" for t in held)
        assert any(t["content"] == "active DM" for t in held)
        assert len(evicted) >= 30
        assert all(cid not in (42, 77) for cid in evicted)
    finally:
        state.close()


def test_age_expiry_notifies_cache_owner_and_clears_activity(tmp_path):
    state = BotState(state_file=str(tmp_path / "state.json"))
    now = time.time()
    evicted = []
    state.memory_channel_retention_s = 60
    state.memory_channel_active_grace_s = 0
    state.max_memory_channels = 100
    state.add_channel_eviction_listener(evicted.append)
    try:
        state.replace_channel_memory(321, [
            {"role": "user", "content": "expired", "timestamp": now - 120}
        ])
        removed = state.prune_channel_memory(now=now)
        assert removed == [321]
        assert evicted == [321]
        assert 321 not in state.channel_memory
        assert 321 not in state.channel_memory_activity
    finally:
        state.close()


def test_summary_compare_and_swap_does_not_overwrite_a_newer_turn(tmp_path):
    state = BotState(state_file=str(tmp_path / "state.json"))
    try:
        state.replace_channel_memory(5, [
            {"role": "user", "content": "first", "timestamp": 1.0},
            {"role": "assistant", "content": "reply", "timestamp": 2.0},
        ])
        snapshot = state.channel_memory_snapshot(5)
        state.append_channel_turn(5, {"role": "user", "content": "newer", "timestamp": 3.0})
        applied = state.apply_channel_history_summary(
            5, snapshot, {"role": "system", "content": "[summary]", "timestamp": 4.0})
        assert applied is False
        assert [turn["content"] for turn in state.channel_memory_snapshot(5)] == [
            "first", "reply", "newer"
        ]
    finally:
        state.close()


def test_append_and_prune_racing_cannot_drop_a_newly_written_active_channel(tmp_path):
    state = BotState(state_file=str(tmp_path / "state.json"))
    state.max_memory_channels = 1
    state.memory_channel_active_grace_s = 3600
    state.replace_channel_memory(8, [
        {"role": "user", "content": "old", "timestamp": time.time() - 7200}
    ])
    barrier = threading.Barrier(2)

    def append():
        barrier.wait()
        state.append_channel_turn(8, {
            "role": "user", "content": "written-during-prune", "timestamp": time.time()
        })

    def prune():
        barrier.wait()
        state.prune_channel_memory()

    try:
        a = threading.Thread(target=append)
        b = threading.Thread(target=prune)
        a.start()
        b.start()
        a.join(timeout=5)
        b.join(timeout=5)
        assert not a.is_alive() and not b.is_alive()
        assert any(t["content"] == "written-during-prune"
                   for t in state.channel_memory_snapshot(8))
    finally:
        state.close()

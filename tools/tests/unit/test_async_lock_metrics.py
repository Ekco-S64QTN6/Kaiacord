"""Regression tests for process-local RPG async lock metrics."""

import asyncio

from utils.infrastructure.monitoring.async_lock_metrics import (
    MeasuredAsyncLock,
    format_lock_registry_metrics,
    lock_registry_snapshot,
    record_registry_lock_created,
)
from utils.ttrpg import character_manager, session_manager


def test_measured_lock_records_contended_waits():
    async def run():
        lock = MeasuredAsyncLock("test_contention")
        await lock.acquire()
        waiter = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        lock.release()
        await waiter
        lock.release()

    before = lock_registry_snapshot().get("test_contention", {})
    asyncio.run(run())
    after = lock_registry_snapshot()["test_contention"]

    assert after["acquisitions"] - before.get("acquisitions", 0) == 2
    assert after["contended"] - before.get("contended", 0) == 1
    assert after["wait_ms_total"] >= before.get("wait_ms_total", 0)


def test_registry_snapshot_records_created_current_and_peak_counts():
    before = lock_registry_snapshot().get("test_registry_size", {})
    record_registry_lock_created(
        "test_registry_size", int(before.get("current", 0)) + 3
    )
    after = lock_registry_snapshot()["test_registry_size"]

    assert after["created"] == before.get("created", 0) + 1
    assert after["current"] == before.get("current", 0) + 3
    assert after["peak"] >= after["current"]


def test_rpg_lock_accessors_register_each_registry(monkeypatch):
    monkeypatch.setattr(session_manager, "_chan_global_lock", asyncio.Lock())
    monkeypatch.setattr(session_manager, "_action_locks", {})
    monkeypatch.setattr(session_manager, "_chan_locks", {})
    monkeypatch.setattr(character_manager, "_global_lock", asyncio.Lock())
    monkeypatch.setattr(character_manager, "_user_locks", {})

    async def run():
        action = await session_manager.get_action_lock("chan:metrics-test")
        action_again = await session_manager.get_action_lock("chan:metrics-test")
        session = await session_manager.get_session_lock("metrics-test")
        user = await character_manager.get_user_lock("metrics-test-user")
        assert action is action_again
        return action, session, user

    asyncio.run(run())
    metrics = lock_registry_snapshot()

    assert metrics["rpg_action"]["current"] >= 1
    assert metrics["rpg_session"]["current"] >= 1
    assert metrics["rpg_character"]["current"] >= 1


def test_sysmon_metrics_are_aggregate_and_do_not_expose_lock_keys():
    for registry in ("rpg_action", "rpg_session", "rpg_character"):
        record_registry_lock_created(registry, 2)

    report = format_lock_registry_metrics()

    assert "Action locks" in report
    assert "Session I/O locks" in report
    assert "Character locks" in report
    assert "metrics-test-user" not in report
    assert "chan:metrics-test" not in report

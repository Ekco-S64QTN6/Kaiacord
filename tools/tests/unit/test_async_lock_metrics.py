"""Regression tests for process-local RPG async lock metrics."""

import asyncio
import gc
import weakref
from weakref import WeakValueDictionary

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
    monkeypatch.setattr(session_manager, "_action_locks", WeakValueDictionary())
    monkeypatch.setattr(session_manager, "_chan_locks", WeakValueDictionary())
    monkeypatch.setattr(character_manager, "_global_lock", asyncio.Lock())
    monkeypatch.setattr(character_manager, "_user_locks", WeakValueDictionary())

    async def run():
        action = await session_manager.get_action_lock("chan:metrics-test")
        action_again = await session_manager.get_action_lock("chan:metrics-test")
        session = await session_manager.get_session_lock("metrics-test")
        user = await character_manager.get_user_lock("metrics-test-user")
        assert action is action_again
        return action, session, user

    retained_locks = asyncio.run(run())
    metrics = lock_registry_snapshot()

    assert metrics["rpg_action"]["current"] >= 1
    assert metrics["rpg_session"]["current"] >= 1
    assert metrics["rpg_character"]["current"] >= 1
    assert len(retained_locks) == 3

    # The registry must not keep idle locks alive after all callers release
    # their strong references.
    del retained_locks
    gc.collect()
    assert len(session_manager._action_locks) == 0
    assert len(session_manager._chan_locks) == 0
    assert len(character_manager._user_locks) == 0
    after = lock_registry_snapshot()
    for name in ("rpg_action", "rpg_session", "rpg_character"):
        assert after[name]["current"] == 0
        assert after[name]["evicted"] >= metrics[name]["evicted"] + 1


def test_sysmon_metrics_are_aggregate_and_do_not_expose_lock_keys():
    for registry in ("rpg_action", "rpg_session", "rpg_character"):
        record_registry_lock_created(registry, 2)

    report = format_lock_registry_metrics()

    assert "Action locks" in report
    assert "Session I/O locks" in report
    assert "Character locks" in report
    assert "metrics-test-user" not in report
    assert "chan:metrics-test" not in report


def test_high_cardinality_lock_registries_return_to_zero_after_idle_gc(monkeypatch):
    monkeypatch.setattr(session_manager, "_chan_global_lock", asyncio.Lock())
    monkeypatch.setattr(session_manager, "_action_locks", WeakValueDictionary())
    monkeypatch.setattr(session_manager, "_chan_locks", WeakValueDictionary())
    monkeypatch.setattr(character_manager, "_global_lock", asyncio.Lock())
    monkeypatch.setattr(character_manager, "_user_locks", WeakValueDictionary())

    async def allocate():
        refs = []
        for i in range(120):
            refs.append(await session_manager.get_action_lock(f"chan:{i}"))
            refs.append(await session_manager.get_action_lock(f"user:{i}"))
            refs.append(await session_manager.get_session_lock(str(i)))
            refs.append(await character_manager.get_user_lock(str(i)))
        return refs

    before = lock_registry_snapshot()
    refs = asyncio.run(allocate())
    assert len(session_manager._action_locks) == 240
    assert len(session_manager._chan_locks) == 120
    assert len(character_manager._user_locks) == 120

    del refs
    gc.collect()

    assert len(session_manager._action_locks) == 0
    assert len(session_manager._chan_locks) == 0
    assert len(character_manager._user_locks) == 0
    after = lock_registry_snapshot()
    for name in ("rpg_action", "rpg_session", "rpg_character"):
        assert after[name]["current"] == 0
        assert after[name]["evicted"] >= before.get(name, {}).get("evicted", 0) + 1


def test_active_owner_and_waiter_keep_one_shared_lock_alive(monkeypatch):
    monkeypatch.setattr(session_manager, "_chan_global_lock", asyncio.Lock())
    monkeypatch.setattr(session_manager, "_action_locks", WeakValueDictionary())

    async def run():
        lock = await session_manager.get_action_lock("chan:active")
        await lock.acquire()
        ref = weakref.ref(lock)
        waiter_has_lock = asyncio.Event()

        async def waiter():
            same_lock = await session_manager.get_action_lock("chan:active")
            assert same_lock is lock
            waiter_has_lock.set()
            await same_lock.acquire()
            same_lock.release()

        task = asyncio.create_task(waiter())
        await waiter_has_lock.wait()
        gc.collect()

        # Both the owner and the queued waiter hold strong references, so
        # another lookup must still find the exact same lock object.
        assert session_manager._action_locks["chan:active"] is lock
        assert await session_manager.get_action_lock("chan:active") is lock

        lock.release()
        await task
        return ref

    ref = asyncio.run(run())
    gc.collect()
    assert ref() is None
    assert "chan:active" not in session_manager._action_locks


def test_lock_metrics_report_idle_evictions():
    record_registry_lock_created("test_evictions", 1)
    class EmptyRegistry:
        def __len__(self):
            return 0

    from utils.infrastructure.monitoring.async_lock_metrics import _record_registry_lock_evicted
    _record_registry_lock_evicted("test_evictions", EmptyRegistry())
    metric = lock_registry_snapshot()["test_evictions"]
    assert metric["current"] == 0
    assert metric["evicted"] == 1

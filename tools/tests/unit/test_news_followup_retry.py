"""Bounded follow-up scheduling for transient grounded-news failures."""
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import utils.core.background_tasks as bg
from utils.core.background_tasks import CoreTaskManager


def _manager(tmp_path, monkeypatch):
    manager = CoreTaskManager.__new__(CoreTaskManager)
    manager.ctx = SimpleNamespace(news_manager=None)
    manager._news_update_lock = asyncio.Lock()
    manager._news_followup_retry_task = None
    manager._news_followup_retry_date = None
    monkeypatch.setattr(bg, "NEWS_DAILY_DIR", Path(tmp_path))
    monkeypatch.setattr(bg, "NEWS_FOLLOWUP_STATE_PATH", Path(tmp_path) / "news_followup_retry.json")
    monkeypatch.setattr(CoreTaskManager, "NEWS_FOLLOWUP_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(bg, "_request_rag_retry", lambda _reason: None)
    return manager


def test_only_one_followup_is_scheduled_per_local_date(tmp_path, monkeypatch):
    async def run():
        manager = _manager(tmp_path, monkeypatch)
        manager.run_news_update = AsyncMock()
        manager._schedule_news_followup_retry()
        first_task = manager._news_followup_retry_task
        manager._schedule_news_followup_retry()
        assert manager._news_followup_retry_task is first_task

        await first_task
        manager._schedule_news_followup_retry()
        assert manager._news_followup_retry_task is None
        assert manager._news_followup_retry_date == datetime.now().strftime("%Y-%m-%d")
        manager.run_news_update.assert_awaited_once()

    asyncio.run(run())


def test_followup_skips_if_today_brief_was_filed_during_wait(tmp_path, monkeypatch):
    async def run():
        manager = _manager(tmp_path, monkeypatch)
        manager.run_news_update = AsyncMock()
        today = datetime.now().strftime("%Y-%m-%d")
        filed = Path(tmp_path) / f"news_brief_{today.replace('-', '')}.md"
        manager._schedule_news_followup_retry()
        filed.write_text("# Already filed", encoding="utf-8")
        await manager._news_followup_retry_task
        manager.run_news_update.assert_not_awaited()

    asyncio.run(run())


def test_scheduled_and_followup_refreshes_are_serialized(tmp_path, monkeypatch):
    async def run():
        manager = _manager(tmp_path, monkeypatch)
        entered = asyncio.Event()
        release = asyncio.Event()
        active = 0
        max_active = 0

        async def body():
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            entered.set()
            await release.wait()
            active -= 1

        manager._run_news_update_body = body
        first = asyncio.create_task(manager.run_news_update())
        await entered.wait()
        second = asyncio.create_task(manager.run_news_update())
        await asyncio.sleep(0)
        assert max_active == 1
        release.set()
        await asyncio.gather(first, second)
        assert max_active == 1

    asyncio.run(run())


def test_daily_cap_survives_a_manager_restart(tmp_path, monkeypatch):
    async def run():
        first = _manager(tmp_path, monkeypatch)
        first.run_news_update = AsyncMock()
        first._schedule_news_followup_retry()
        await first._news_followup_retry_task
        first.run_news_update.assert_awaited_once()

        restarted = _manager(tmp_path, monkeypatch)
        restarted.run_news_update = AsyncMock()
        restarted._schedule_news_followup_retry()
        assert restarted._news_followup_retry_task is None
        restarted.run_news_update.assert_not_awaited()

    asyncio.run(run())

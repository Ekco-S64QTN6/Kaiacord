"""Every caller of refresh_knowledge_base must handle its completion result."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_standalone_reindex_cli_refuses_to_report_incomplete_refresh_as_success():
    source = _source("tools/maintenance/reindex_rag.py")
    assert "if await rag.refresh_knowledge_base() is not True:" in source
    assert "raise RuntimeError(\"Full RAG refresh did not complete" in source
    assert "raise RuntimeError(f\"Target file re-index did not complete" in source


def test_discord_reindex_command_queues_retry_on_refresh_or_persist_failure():
    source = _source("utils/commands/reindex_handler.py")
    assert "refresh_completed = await run_rag(rag.refresh_knowledge_base)" in source
    assert "if refresh_completed is not True:" in source
    assert "if persist_result is False:" in source
    assert source.count("request_reindex()") >= 2


def test_startup_does_not_claim_rag_refresh_succeeded_when_it_did_not():
    source = _source("Kaiacord.py")
    assert "refresh_completed = await run_rag(ctx.rag.refresh_knowledge_base)" in source
    assert "if refresh_completed is True:" in source
    assert 'request_reindex()' in source
    startup_except = source.split("except Exception as e:", 1)[1].split("# 3e.", 1)[0]
    assert "request_reindex()" in startup_except


def test_dream_and_news_refreshes_queue_retry_on_false_or_timeout():
    source = _source("utils/core/background_tasks.py")
    assert "refresh_completed = await asyncio.wait_for(" in source
    assert '_request_rag_retry("post-dream refresh")' in source
    assert '_request_rag_retry("post-dream refresh timeout")' in source
    assert '_request_rag_retry("post-dream refresh error")' in source
    assert "except Exception as refresh_error:" in source
    assert "rag_refresh_completed = False" in source
    assert 'log_error(f"Daily news RAG refresh raised: {refresh_error}")' in source
    assert "rag_refresh_completed = await run_rag_func(self.ctx.rag.refresh_knowledge_base) is True" in source
    assert '_request_rag_retry("daily news refresh")' in source

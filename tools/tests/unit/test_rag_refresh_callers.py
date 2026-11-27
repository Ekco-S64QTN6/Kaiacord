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


def test_live_bot_refuses_standalone_incremental_and_single_file_reindex(
    tmp_path, monkeypatch, capsys
):
    """A live bot owns the in-memory index; non-clear CLI runs must not open a second owner."""
    import asyncio

    from tools.maintenance import reindex_rag

    constructed = []

    monkeypatch.setattr(reindex_rag, "_bot_running", lambda: True)
    monkeypatch.setattr(reindex_rag, "KaiaRAG", lambda: constructed.append(True))

    for clear_storage, file_path in (
        (False, None),
        (False, str(tmp_path / "document.md")),
        (True, None),
    ):
        result = asyncio.run(
            reindex_rag.rebuild_rag(
                clear_storage=clear_storage,
                file_path=file_path,
                force=False,
            )
        )
        assert result is False

    assert constructed == []
    stderr = capsys.readouterr().err
    assert stderr.count("REFUSED:") == 3
    assert "--trigger" in stderr
    assert "--force" in stderr


def test_trigger_reindex_requests_live_bot_refresh_without_constructing_rag(
    monkeypatch,
):
    """The supported live-bot route only requests work from the existing owner."""
    from utils.core import rag_utils
    from tools.maintenance import reindex_rag

    requested = []
    monkeypatch.setattr(rag_utils, "request_reindex", lambda: requested.append(True))
    monkeypatch.setattr(
        reindex_rag,
        "KaiaRAG",
        lambda: (_ for _ in ()).throw(AssertionError("trigger must not construct KaiaRAG")),
    )

    reindex_rag.trigger_bot_reindex()

    assert requested == [True]

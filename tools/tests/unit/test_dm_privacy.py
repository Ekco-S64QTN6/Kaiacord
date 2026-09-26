"""A DM is written to its own log under memory/, never to the shared
user_logs that retrieval serves to public replies."""
import inspect

from utils.core import dm_log


def test_a_dm_goes_to_its_own_log(tmp_path, monkeypatch):
    monkeypatch.setattr(dm_log, "telemetry_path", lambda p: str(tmp_path / p))
    dm_log.record(519557167779676160, "Starkind", "this is between us", "understood.")
    p = tmp_path / "memory" / "dm_logs" / "519557167779676160.md"
    text = p.read_text()
    assert "Starkind: this is between us" in text and "Kaia: understood." in text
    assert "knowledge_base" not in str(p)


def test_the_pipeline_routes_dms_away_from_the_shared_log():
    from utils.core.message_processor import MessageProcessor
    src = inspect.getsource(MessageProcessor._background_logging_and_memory)
    dm = src.index('getattr(ctx, "is_dm", False)')
    shared = src.index("self.rag.log_user_interaction_async(")
    assert dm < shared and "elif not _is_style_drifted" in src

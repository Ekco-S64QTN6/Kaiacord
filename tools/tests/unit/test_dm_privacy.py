"""A DM is written to its own log under memory/, never to the shared
user_logs that retrieval serves to public replies."""
import ast
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace

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


def test_a_dm_never_becomes_one_of_her_notes():
    """Notes are indexed and retrieval serves public replies."""
    src = Path("utils/core/message_processor.py").read_text()
    gate = src[src.index("from utils.core import kaia_notes") - 400: src.index("from utils.core import kaia_notes")]
    assert '"is_dm"' in gate



def test_private_dm_does_not_update_cross_channel_memory():
    """Private turns must not feed stores that are injected into later public turns."""
    from utils.core.message_processor import MessageProcessor

    source = textwrap.dedent(inspect.getsource(MessageProcessor._background_logging_and_memory))
    tree = ast.parse(source)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    guarded_names = {
        "learn_from_interaction", "update_relationship", "save_event_async",
        "record_claim", "note_argument", "emotional_arc", "observe_exchange",
        "desire_engine", "_write_and_rotate_growth_log", "_find_open_loop",
        "write_atomic", "pending_afterthoughts",
    }
    found = set()
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        if name not in guarded_names:
            continue
        found.add(name)
        parent = parents.get(node)
        guarded = False
        while parent is not None:
            if isinstance(parent, ast.If) and ast.unparse(parent.test) == "not is_private_dm":
                guarded = True
                break
            parent = parents.get(parent)
        assert guarded, f"{name} can still be reached by a private DM"
    assert guarded_names <= found, f"privacy audit lost coverage for {guarded_names - found}"


def test_private_dm_does_not_change_the_cross_channel_user_state():
    from utils.core.message_processor import MessageProcessor

    source = inspect.getsource(MessageProcessor._retrieve_and_generate)
    assert "if not _is_private_dm(ctx):\n                    self.bot_state.update_user_state" in source


def test_private_dm_predicate_is_explicit():
    from utils.core.message_processor import _is_private_dm

    assert _is_private_dm(SimpleNamespace(is_dm=True)) is True
    assert _is_private_dm(SimpleNamespace(is_dm=False)) is False
    assert _is_private_dm(SimpleNamespace()) is False


def test_dm_interaction_does_not_become_the_proactive_target(tmp_path):
    from utils.infrastructure.system.bot_state import BotState

    state = BotState(state_file=str(tmp_path / "bot_state.json"))
    state.update_interaction(None)
    assert state.last_interaction_time > 0
    assert state.channel_last_activity == {}
    assert state.last_active_channel_id is None
    state._executor.shutdown(wait=True)

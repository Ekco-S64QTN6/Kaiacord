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


def _log_turn(is_dm, monkeypatch, reply="understood."):
    """Run the real background step for one turn; return (shared log calls, dm log calls)."""
    import asyncio
    from utils.core.message_context import MessageContext
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config

    shared, private = [], []

    class Rag:
        async def log_user_interaction_async(self, *a):
            shared.append(a)

    class State:
        relationships, pending_afterthoughts = {}, []
        def channel_memory_snapshot(self, cid): return []
        def append_channel_turns(self, *a, **k): pass
        def update_relationship(self, *a, **k): pass
        def save(self): pass

    class Learner:
        async def learn_from_interaction(self, *a): pass

    monkeypatch.setattr(dm_log, "record", lambda *a: private.append(a))
    # The public turn also moves her mood, needs and relationships; none of it is
    # this test's business, and all of it is live state under memory/.
    from utils.core import kaia_mood, kaia_desires, relationship_manager, conversation_beliefs
    monkeypatch.setattr(kaia_mood.emotional_arc, "update", lambda *a, **k: None)
    monkeypatch.setattr(kaia_desires.desire_engine, "observe_exchange", lambda *a, **k: None)
    monkeypatch.setattr(relationship_manager, "detect_event_type", lambda *a, **k: None)
    monkeypatch.setattr(conversation_beliefs, "note_argument", lambda *a, **k: None)
    monkeypatch.setattr(MessageProcessor, "__module__", MessageProcessor.__module__)
    p = MessageProcessor.__new__(MessageProcessor)
    p.config, p.rag, p.bot_state, p.personalization_engine = config, Rag(), State(), Learner()
    p.stats_tracker = SimpleNamespace(record_response_time=lambda t: None)
    p._bg_semaphore = asyncio.Semaphore(1)
    author = SimpleNamespace(id=1, name="Starkind", display_name="Starkind")
    msg = SimpleNamespace(author=author, attachments=[], embeds=[], stickers=[], content="this is between us",
                          channel=SimpleNamespace(id=7), guild=None if is_dm else object(), platform="discord")
    ctx = MessageContext(message=msg, sanitized_content=msg.content, is_social=True, is_mention=True,
                         is_dm=is_dm, start_time=0.0)
    ctx.response_text = reply
    asyncio.run(p._background_logging_and_memory(ctx))
    return shared, private


def test_the_pipeline_routes_dms_away_from_the_shared_log(monkeypatch):
    shared, private = _log_turn(True, monkeypatch)
    assert private and not shared
    shared, private = _log_turn(False, monkeypatch)
    assert shared and not private


def test_a_reply_full_of_ellipses_is_still_logged(monkeypatch):
    """The user's own message went unlogged with a reply the style check disliked."""
    shared, _ = _log_turn(False, monkeypatch, reply="well… it's… complicated… isn't it… yes… — — — — —")
    assert shared and shared[0][2] == "this is between us"


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
        "desire_engine", "append_growth_event", "_find_open_loop",
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
            if isinstance(parent, ast.If) and "not is_private_dm" in ast.unparse(parent.test):
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
    state.close()



def test_server_wide_private_monologue_does_not_enter_direct_reply_prompts():
    """Cross-channel thoughts are unscoped; they must not steer direct replies."""
    from utils.core.message_processor import MessageProcessor

    source = textwrap.dedent(inspect.getsource(MessageProcessor._retrieve_and_generate))
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "get_injection"
        for node in ast.walk(tree)
    ), "direct replies must not inject the private monologue buffer"
    assert "self.ctx.monologue" not in source
    assert "monologue.get_injection()" not in Path("utils/core/message_processor.py").read_text(
        encoding="utf-8"
    )


def test_background_tasks_do_not_expose_monologue_to_message_processor():
    source = Path("utils/core/background_tasks.py").read_text(encoding="utf-8")
    assert "ctx.monologue = self.monologue" not in source

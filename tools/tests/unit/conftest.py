"""Harnesses for driving one turn through the real message pipeline offline."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def build_messages():
    """build_messages(text, author="Ekco", parent_context=None) -> the messages
    `_construct_messages` would send to the model for that turn."""
    from utils.core.message_context import MessageContext
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config

    def build(text, author="Ekco", parent_context=None):
        who = MagicMock()
        who.display_name = who.name = author
        who.id = 1
        msg = MagicMock()
        msg.platform, msg.author, msg.content = "discord", who, text
        msg.attachments, msg.embeds, msg.stickers = [], [], []
        msg.channel.id = 1
        ctx = MessageContext(message=msg, sanitized_content=text, is_social=False, is_mention=True,
                             is_dm=False, parent_context=parent_context, start_time=0.0)
        p = MessageProcessor.__new__(MessageProcessor)
        p.config = config
        return p._construct_messages(ctx, {"persona": "P", "rag": "", "history": []})

    return build


@pytest.fixture
def log_turn(monkeypatch):
    """log_turn(is_dm, text="this is between us", reply="understood.") runs the real
    background logging step and returns what reached each store:
    {"shared": [...], "private": [...], "events": [...]}. Her mood, needs and
    belief arguments are live state under memory/ and are patched out."""
    from utils.core import dm_log, kaia_mood, kaia_desires, relationship_manager, conversation_beliefs
    from utils.core.message_context import MessageContext
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config

    seen = {"shared": [], "private": [], "events": []}

    class Rag:
        async def log_user_interaction_async(self, *a):
            seen["shared"].append(a)

    class State:
        relationships, pending_afterthoughts = {}, []
        def channel_memory_snapshot(self, cid): return []
        def append_channel_turns(self, *a, **k): pass
        def update_relationship(self, *a, **k): pass
        def save(self): pass

    class Learner:
        async def learn_from_interaction(self, *a): pass

    monkeypatch.setattr(dm_log, "record", lambda *a: seen["private"].append(a))
    monkeypatch.setattr(kaia_mood.emotional_arc, "update", lambda *a, **k: None)
    monkeypatch.setattr(kaia_desires.desire_engine, "observe_exchange", lambda *a, **k: None)
    monkeypatch.setattr(relationship_manager, "detect_event_type",
                        lambda own, reply: seen["events"].append((own, reply)))
    monkeypatch.setattr(conversation_beliefs, "note_argument", lambda *a, **k: None)

    def run(is_dm, text="this is between us", reply="understood."):
        p = MessageProcessor.__new__(MessageProcessor)
        p.config, p.rag, p.bot_state, p.personalization_engine = config, Rag(), State(), Learner()
        p.stats_tracker = SimpleNamespace(record_response_time=lambda t: None)
        p._bg_semaphore = asyncio.Semaphore(1)
        author = SimpleNamespace(id=1, name="Starkind", display_name="Starkind")
        msg = SimpleNamespace(author=author, attachments=[], embeds=[], stickers=[], content=text,
                              channel=SimpleNamespace(id=7), guild=None if is_dm else object(),
                              platform="discord")
        ctx = MessageContext(message=msg, sanitized_content=text, is_social=True, is_mention=True,
                             is_dm=is_dm, start_time=0.0)
        ctx.response_text = reply
        asyncio.run(p._background_logging_and_memory(ctx))
        return seen

    return run

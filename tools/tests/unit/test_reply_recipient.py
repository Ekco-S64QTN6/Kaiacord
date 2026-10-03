"""Whom one of her own messages was answering, when someone replies to it."""
from collections import deque
from types import SimpleNamespace

import pytest

from utils.core.context_enricher import ContextEnricher
from utils.infrastructure.system.bot_state import bot_state

CH = 4242


@pytest.fixture
def memory(monkeypatch):
    mem = {}
    monkeypatch.setattr(bot_state, "channel_memory", mem)
    return mem


def _who(content, guild=None):
    return ContextEnricher._bot_message_recipient(SimpleNamespace(id=CH), content, guild)


def test_a_reply_to_a_quip_names_no_recipient(memory):
    """GuardNGnowm replied to a quip and was answered as "ekco", the last
    person to have spoken before it."""
    memory[CH] = deque([
        {"role": "user", "content": "Ekco: night all"},
        {"role": "assistant", "content": "starbase is a city now, apparently.", "unprompted": True},
    ])
    assert _who("*Idle thought* starbase is a city now, apparently.") is None


def test_a_reply_to_an_answer_names_who_she_answered(memory):
    memory[CH] = deque([
        {"role": "user", "content": "Starkind: what is ozone"},
        {"role": "assistant", "content": "three oxygen atoms, and a smell after storms."},
    ])
    assert _who("three oxygen atoms, and a smell after storms.") == "Starkind"


def test_an_opening_name_counts_only_if_someone_here_has_it(memory):
    guild = SimpleNamespace(members=[SimpleNamespace(display_name="Starkind")])
    assert _who("starkind, that's the one.", guild) == "starkind"
    assert _who("sissy spacex, i assume?", guild) is None
    assert _who("honestly, no.", guild) is None


def test_nothing_known_is_nobody(memory):
    assert _who("a quiet night on the bands.") is None

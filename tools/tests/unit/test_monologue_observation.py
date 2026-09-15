"""The inner monologue observes her Discord server — and only that.

For a day and a half every thought she had was about one Project 1999 forum
poster: twenty consecutive `channel_observation` entries, all opening "i wonder
if bradzax". Three separate defects stacked up to produce it, and each is
pinned here.
"""
import asyncio

import pytest

from utils.core.kaia_monologue import InnerMonologue


class _FakeOllama:
    """Records the prompt it was handed instead of generating."""

    def __init__(self):
        self.prompts = []

    async def chat(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        return {"message": {"content": "i notice the room has gone quiet."}}


class _BotState:
    pass


def _turns(*rows):
    """rows of (name, text, when, external) -> channel_memory turn dicts."""
    out = []
    for name, text, when, external in rows:
        turn = {"role": "user", "content": f"{name}: {text}", "timestamp": when}
        if external:
            turn["external"] = external
        out.append(turn)
    return out


def _observe(monologue, channel_memory):
    monologue._last_generated = 0
    ollama = _FakeOllama()
    asyncio.run(monologue.generate_thought(
        channel_memory=channel_memory, bot_state=_BotState(),
        ollama_client=ollama, chat_model="test-model"))
    return ollama.prompts[0] if ollama.prompts else None


def test_forum_posts_are_not_mistaken_for_her_discord_server():
    """`channel_memory` is shared, and forum threads are seeded into it.

    `forum_drafting.seed_thread_history` stores a thread under a key from
    `conversation_channel_id`, which is a plain int (crc32 % 10**10) — so a
    thread is indistinguishable from a channel by its key, and its turns are
    formatted exactly like Discord ones. Live state held 24 Discord turns
    against 31 forum turns, so "your Discord server" was mostly the forum.
    """
    channel_memory = {
        "1462239450691145924": _turns(("Ekco", "the reindex finished", 1000.0, None)),
        "222746109": _turns(("bradzax", "kids today have no idea", 2000.0, "vbulletin")),
        "1592286285": _turns(("bradzax", "back in ninety eight", 3000.0, "vbulletin")),
    }
    prompt = _observe(InnerMonologue(), channel_memory)
    assert prompt is not None
    assert "bradzax" not in prompt.lower(), "a forum poster reached the monologue"
    assert "reindex finished" in prompt


def test_the_window_is_the_most_recent_across_channels():
    """The tail was taken from a dict-order concatenation with no sort.

    Whichever channel was inserted last supplied every one of the final eight
    lines regardless of when those messages arrived.
    """
    channel_memory = {
        "111111111111111111": _turns(("Ekco", "newest thing", 9000.0, None)),
        "222222222222222222": _turns(("Starkind", "ancient thing", 10.0, None)),
    }
    prompt = _observe(InnerMonologue(), channel_memory)
    newest, ancient = prompt.index("newest thing"), prompt.index("ancient thing")
    assert ancient < newest, "messages were not ordered by time"


def test_an_unchanged_window_is_not_observed_twice():
    """The guard compared message *count*, not content.

    An unchanged conversation whose count shifted by one was re-observed as
    though it were new, which is how the same stale window produced another
    thought about it every fifteen minutes.
    """
    monologue = InnerMonologue()
    window = {"111111111111111111": _turns(
        ("Ekco", "one", 1.0, None), ("Ekco", "two", 2.0, None))}
    assert _observe(monologue, window) is not None
    assert _observe(monologue, window) is None, "re-observed identical content"


def test_different_content_of_the_same_length_is_observed():
    """The other half of the same defect: equal counts were treated as 'no new
    activity', so a whole conversation could pass unnoticed."""
    monologue = InnerMonologue()
    first = {"111111111111111111": _turns(
        ("Ekco", "one", 1.0, None), ("Ekco", "two", 2.0, None))}
    second = {"111111111111111111": _turns(
        ("Ekco", "three", 3.0, None), ("Ekco", "four", 4.0, None))}
    assert _observe(monologue, first) is not None
    assert _observe(monologue, second) is not None, "same count, new content, skipped"


def test_seeded_forum_turns_carry_a_float_timestamp_and_the_external_mark():
    """`seed_thread_history` wrote `str(time.time())`, so anything sorting the
    merged history numerically threw or fell back to insertion order."""
    import inspect

    from utils.social import forum_drafting

    src = inspect.getsource(forum_drafting.seed_thread_history)
    assert '"timestamp": time.time()' in src, "timestamp is not a float"
    assert '"external": PLATFORM' in src, "seeded turns are not marked external"
    assert "str(time.time())" not in src


def test_typographic_punctuation_is_folded_to_plain_english():
    """`monologue_log.jsonl` read "bradzax\\u2019s".

    The model reaches for curly quotes, em dashes and a single-glyph ellipsis;
    nothing folded them, and `json.dumps` escapes any non-ASCII, so the log and
    anything echoing it showed escapes instead of English.
    """
    import json

    from utils.core.sanitizer import to_plain_english

    raw = "i wonder if bradzax’s “nostalgia” — late ’90s … is a defence"
    plain = to_plain_english(raw)

    assert "'" in plain and "’" not in plain
    assert '"' in plain and "“" not in plain
    assert "-" in plain and "—" not in plain
    assert "..." in plain and "…" not in plain
    # and it survives a JSON round trip without escapes
    assert "\\u" not in json.dumps(plain)


def test_normalisation_leaves_real_words_alone():
    """Deliberately narrow: folding accents would mangle somebody's name."""
    from utils.core.sanitizer import to_plain_english

    assert to_plain_english("café naïve Ekco") == "café naïve Ekco"
    assert to_plain_english("") == ""
    assert to_plain_english("plain ascii stays put") == "plain ascii stays put"


def test_the_monologue_normalises_what_it_stores():
    """The fold has to happen where the thought is made, not at each consumer."""
    import inspect

    from utils.core import kaia_monologue

    src = inspect.getsource(kaia_monologue.InnerMonologue.generate_thought)
    assert "to_plain_english" in src, "the thought is stored unnormalised"


def test_the_two_broadcasts_are_independently_switchable():
    """One switch for both would mean silencing a few considered summaries a
    day to stop a passing thought every fifteen minutes."""
    import inspect

    from utils.core.background_tasks import CoreTaskManager

    mono = inspect.getsource(CoreTaskManager._broadcast_monologue)
    digest = inspect.getsource(CoreTaskManager._broadcast_observation_digest)

    assert 'config.get("monologue.broadcast_to_chat"' in mono
    assert 'config.get("observation.broadcast_digest"' in digest
    assert "monologue.broadcast_to_chat" not in digest
    assert "observation.broadcast_digest" not in mono
    # both land in her own channel, not wherever someone last spoke
    assert 'name="kaia-opolis"' in mono
    assert 'name="kaia-opolis"' in digest


def test_the_digest_broadcast_sends_the_digest_and_not_a_reaction_to_it():
    """Three runs logged "Observation digest broadcast to chat" and none of
    them spoke the observation.

    The digest was handed to `_dispatch_proactive`, which passed it to
    `generate_opener` as hidden context and sent the one-liner that came back:

        digest: "I noticed they were spiraling about AI regulation, financial
                 instability, and some bizarre online cults"
        sent:   "i saw something similar. it's just the internet being the
                 internet, isn't it?"

    The summary is the whole point of generating it, so the summary is what
    gets sent.
    """
    import inspect

    from utils.core.background_tasks import CoreTaskManager

    src = inspect.getsource(CoreTaskManager._broadcast_observation_digest)
    body = "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))

    assert "send_kaia_response(channel, f\"{label} {text}\")" in body, \
        "the digest text is not what gets sent"
    assert "_dispatch_proactive" not in body, \
        "still routing through the opener generator, which discards the digest"
    assert "generate_opener" not in body
    assert "to_plain_english" in body, "digest is sent without normalising punctuation"


def test_legacy_untagged_forum_turns_are_still_excluded():
    """The `external` marker only covers turns seeded after it was added.

    Two of four forum channels in the live bot_state.json carry no marker —
    they were persisted before the fix — which is how a thought about a forum
    poster ("i wonder if bradzax is intentionally trying to trigger reiwa")
    reached the log hours afterwards. Asking Discord whether the channel
    exists covers those; a crc32 conversation id can never resolve.
    """
    import asyncio

    from utils.core.kaia_monologue import InnerMonologue

    channel_memory = {
        # real snowflake, resolves
        "1462239450691145924": [
            {"role": "user", "content": "Ekco: the reindex finished",
             "timestamp": 1000.0}],
        # legacy forum thread: pseudo-id, and crucially NO external marker
        "1592286285": [
            {"role": "user", "content": "Reiwa: probably meant 1952",
             "timestamp": 2000.0}],
    }
    resolver = lambda cid: str(cid) == "1462239450691145924"

    captured = {}

    class _Fake:
        async def chat(self, **kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            return {"message": {"content": "i notice it is quiet."}}

    class _State:
        pass

    monologue = InnerMonologue()
    monologue._last_generated = 0
    asyncio.run(monologue.generate_thought(
        channel_memory=channel_memory, bot_state=_State(),
        ollama_client=_Fake(), chat_model="test-model",
        is_discord_channel=resolver))

    prompt = captured["prompt"]
    assert "reindex finished" in prompt
    assert "Reiwa" not in prompt, "an untagged forum turn still reached the monologue"


def test_both_broadcasts_are_labelled():
    """Unlabelled, an aired thought read as a random remark in the channel."""
    import inspect

    from utils.core.background_tasks import CoreTaskManager

    mono = inspect.getsource(CoreTaskManager._broadcast_monologue)
    digest = inspect.getsource(CoreTaskManager._broadcast_observation_digest)

    assert 'config.get("monologue.broadcast_prefix"' in mono
    assert 'config.get("observation.broadcast_prefix"' in digest
    assert 'f"{label} ' in mono and 'f"{label} ' in digest


def test_a_late_night_thought_is_not_withheld():
    """Three thoughts in one evening were generated, logged and silently
    dropped — 23:02, 23:31 and 23:48, the last directly about a question Ekco
    had just asked her — because the monologue obeyed the proactive engine's
    09:00-22:00 window.

    That was the wrong comparison. A proactive opener interrupts someone in a
    channel they are reading; a thought in #kaia-opolis is her talking to
    herself in her own room. The daily cap and minimum interval still apply.
    """
    import asyncio
    from unittest.mock import MagicMock, patch

    from utils.core.background_tasks import CoreTaskManager
    from utils.infrastructure.system import yaml_config

    def _air(respect_quiet_hours):
        manager = CoreTaskManager.__new__(CoreTaskManager)
        manager.ctx = MagicMock()
        manager.ctx.bot_state.monologue_broadcast_date = ""
        manager.ctx.bot_state.monologue_broadcast_count = 0
        manager.ctx.bot_state.monologue_broadcast_last_sent = 0.0
        engine = MagicMock()
        engine.is_within_hours.return_value = False        # 23:48
        manager.proactive_engine = engine

        real_get = yaml_config.config.get

        def fake_get(key, default=None):
            if key == "monologue.broadcast_to_chat":
                return True
            if key == "monologue.respect_quiet_hours":
                return respect_quiet_hours
            return real_get(key, default)

        async def _noop(channel, text):
            return None

        with patch.object(yaml_config.config, "get", fake_get), \
             patch("discord.utils.get", return_value=MagicMock(id=1)), \
             patch("utils.infrastructure.system.messaging.send_kaia_response", _noop):
            return asyncio.run(manager._broadcast_monologue("a late thought"))

    assert _air(respect_quiet_hours=False) is True, \
        "a thought at 23:48 was withheld"
    assert _air(respect_quiet_hours=True) is False, \
        "the opt-in quiet-hours gate no longer works"


def test_the_proactive_window_is_configurable():
    """`QUIET_HOUR_START`/`QUIET_HOUR_END` were hardcoded, so changing when she
    may speak first meant editing source."""
    import inspect

    from utils.core.kaia_proactive import ProactiveEngine

    src = inspect.getsource(ProactiveEngine._is_within_hours)
    assert "proactive.quiet_hour_start" in src
    assert "proactive.quiet_hour_end" in src

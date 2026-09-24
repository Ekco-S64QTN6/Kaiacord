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






def test_only_the_absence_checkin_goes_out_unlabelled():
    """An absence trigger is addressed to a named person — a check-in, not a
    musing — so the thought label would misdescribe it.

    The first version of this exception keyed on `target_user` being set, on the
    assumption that only an absence check-in carries one. Three other sources
    populate it with the person the thought is *about*: `conversation_followup`
    (SOURCE_WEIGHTS 35, the highest of all), `personal_memory` (25) and
    `anchor_callback` (15). So the presence test silenced the label on most
    openers — including the 02:04 `conversation_followup` this was written for.

    Asserted against every declared source rather than a hand-built case,
    because the bug was in which sources reach the branch.
    """
    import inspect

    from utils.core.background_tasks import CoreTaskManager
    from utils.core.kaia_proactive import SOURCE_WEIGHTS

    src = inspect.getsource(CoreTaskManager._dispatch_proactive)
    assert 'getattr(trigger, "trigger_type", "") == "absence"' in src, \
        "the exception is keyed on something other than the trigger type"
    assert '"target_user"' not in src, \
        "target_user is set by three non-absence sources; it cannot gate the label"

    # Every weighted source is a musing and must keep its label. "absence" is
    # deliberately not in SOURCE_WEIGHTS — it is checked before the weighted
    # draw — which is why it is named explicitly here.
    for source in SOURCE_WEIGHTS:
        assert source != "absence"



def test_every_broadcast_gate_field_survives_a_restart():
    """`BotState` names each persisted field in three places — the attribute,
    `load()` and `save()`. The monologue's own gate fields were once in none of
    them, so she aired a thought two minutes after every restart against a
    90-minute minimum. The shared unprompted gate is the one left; check it.
    """
    import inspect

    from utils.infrastructure.system.bot_state import BotState

    src = inspect.getsource(BotState)
    missing = [f"{f} ({src.count(f)} mention(s), needs 3)"
               for f in ("unprompted_last_sent", "unprompted_count", "unprompted_date")
               if src.count(f) < 3]
    assert not missing, f"broadcast gate fields not round-tripped: {missing}"


def test_the_unprompted_gate_actually_round_trips(tmp_path):
    """The source check above cannot see a typo'd key string. This writes the
    state, reads it back from disk, and compares — through the constructor
    argument, never the live memory/bot_state.json.
    """
    import json

    from utils.infrastructure.system.bot_state import BotState

    path = tmp_path / "bot_state.json"
    s = BotState(state_file=str(path))
    s.unprompted_last_sent = 1234.5
    s.unprompted_count = 4
    s.unprompted_date = "2026-09-21"
    s.save()
    # save() offloads the write to a single-worker executor; wait for it.
    s._executor.shutdown(wait=True)

    raw = json.loads(path.read_text()) if path.exists() else {}
    assert raw.get("unprompted_last_sent") == 1234.5, f"not written to disk: {sorted(raw)[:12]}"
    assert raw.get("unprompted_count") == 4
    assert raw.get("unprompted_date") == "2026-09-21"


# ── Posting through the shared unprompted system ────────────────────────────
def _manager(config_values, sent):
    """A CoreTaskManager wired to a fake #kaia-opolis and a controlled config."""
    import types
    from unittest.mock import MagicMock

    from utils.core import unprompted
    from utils.core.background_tasks import CoreTaskManager

    class Channel:
        id = 7
        name = "kaia-opolis"

        async def send(self, text):
            sent.append(text)

        def typing(self):
            class _T:
                async def __aenter__(self): return None
                async def __aexit__(self, *a): return False
            return _T()

    manager = CoreTaskManager.__new__(CoreTaskManager)
    state = types.SimpleNamespace(unprompted_date="", unprompted_count=0,
                                  unprompted_last_sent=0.0, channel_memory={},
                                  is_generating=False, boot_complete=True)
    state.save = lambda: None
    manager.ctx = types.SimpleNamespace(bot=MagicMock(), bot_state=state)
    manager.proactive_engine = MagicMock()

    class Cfg:
        max_memory_messages = 10

        @staticmethod
        def get(key, default=None):
            return config_values.get(key, default)

    return manager, Channel(), Cfg


def _run(coro_fn, config_values):
    import asyncio
    from unittest.mock import patch

    from utils.core import unprompted

    sent = []
    manager, channel, cfg = _manager(config_values, sent)
    with patch.object(unprompted, "_config", lambda: cfg), \
         patch("discord.utils.get", return_value=channel), \
         patch("asyncio.sleep", _instant):
        result = asyncio.run(coro_fn(manager))
    return result, sent


async def _instant(*_a, **_k):
    return None


def test_the_digest_is_what_gets_sent():
    """Three runs logged "Observation digest broadcast to chat" and none of
    them spoke the observation: the digest went to `generate_opener` as hidden
    context and the one-liner that came back was sent instead. The summary is
    the point of generating it, so the summary is what gets sent — under the
    Observation label, which it always wears."""
    digest = "I noticed they were arguing about AI regulation and online cults."
    ok, sent = _run(lambda m: m._broadcast_observation_digest(digest, 1.0),
                    {"unprompted.min_interval_minutes": 0})
    assert ok is True
    assert sent == [f"💭 **Observation:** {digest}"]


def test_the_monologue_and_the_digest_switch_independently():
    """Silencing a thought every fifteen minutes must not silence a few
    considered summaries a day, or the other way round."""
    cfg = {"unprompted.sources.monologue": False, "unprompted.min_interval_minutes": 0}
    ok, sent = _run(lambda m: m._broadcast_monologue("a thought."), cfg)
    assert ok is False and sent == []
    ok, sent = _run(lambda m: m._broadcast_observation_digest("a summary.", 1.0), cfg)
    assert ok is True and sent


def test_a_late_night_thought_is_not_withheld_unless_asked():
    """23:48 thoughts were generated, logged and silently dropped because the
    monologue obeyed a 09:00-22:00 window nobody had chosen for it. The window
    is one opt-in setting for everything unprompted now."""
    from datetime import datetime
    from unittest.mock import patch

    base = {"unprompted.sources.monologue": True, "unprompted.min_interval_minutes": 0,
            "unprompted.quiet_hour_start": 9, "unprompted.quiet_hour_end": 22}
    with patch("utils.core.unprompted.datetime") as dt:
        dt.now.return_value = datetime(2026, 9, 20, 23, 48)
        dt.fromtimestamp = datetime.fromtimestamp
        ok, _ = _run(lambda m: m._broadcast_monologue("a late thought."),
                     {**base, "unprompted.respect_quiet_hours": False})
        assert ok is True, "a thought at 23:48 was withheld"
        ok, _ = _run(lambda m: m._broadcast_monologue("a late thought."),
                     {**base, "unprompted.respect_quiet_hours": True})
        assert ok is False, "the opt-in posting hours no longer apply"


def test_the_opener_is_labelled_but_a_checkin_is_not():
    """An opener that arrives bare reads as a remark aimed at whoever spoke
    last. An absence check-in is the exception: it is addressed to a named
    person, so a musing label would misdescribe it — and keying that on
    `target_user` silenced the label on most openers, since three other
    sources set it to the person the thought is *about*."""
    import types
    from unittest.mock import AsyncMock, MagicMock

    def dispatch(trigger_type):
        async def go(manager):
            manager.ctx.bot.get_channel.return_value = _CHANNEL
            manager.proactive_engine.generate_opener = AsyncMock(return_value="been a while.")
            manager.ctx.ollama_client = MagicMock()
            trigger = types.SimpleNamespace(channel_id=7, trigger_type=trigger_type,
                                            context="", target_user="starkind",
                                            content_id="")
            from unittest.mock import patch
            with patch("utils.social.kaia_social_responder.load_persona_async",
                       AsyncMock(return_value="")):
                return await manager._dispatch_proactive(trigger)
        return go

    global _CHANNEL
    sent = []

    class _Ch:
        id = 7
        guild = object()

        async def send(self, text):
            sent.append(text)

        def typing(self):
            class _T:
                async def __aenter__(self): return None
                async def __aexit__(self, *a): return False
            return _T()

    _CHANNEL = _Ch()
    ok, _ = _run(dispatch("conversation_followup"), {"unprompted.min_interval_minutes": 0,
                                                     "unprompted.rotate": False})
    assert ok and sent[-1] == "☕ **Apropos of nothing:** been a while."
    ok, _ = _run(dispatch("absence"), {"unprompted.min_interval_minutes": 0})
    assert ok and sent[-1] == "been a while."


_CHANNEL = None


def test_a_failed_thought_is_retried_on_the_same_conversation():
    """The window was marked as thought about before the model was called, so
    one timeout meant that conversation was never thought about at all."""
    import asyncio
    from collections import deque

    from utils.core.kaia_monologue import InnerMonologue

    calls = {"n": 0}

    class Flaky:
        async def chat(self, **_):
            calls["n"] += 1
            if calls["n"] == 1:
                raise asyncio.TimeoutError()
            return {"message": {"content": "i notice ekco keeps coming back to the same bug."}}

    memory = {1: deque([{"role": "user", "content": "Ekco: the cron job failed again",
                         "timestamp": 1.0}])}
    mono = InnerMonologue()
    first = asyncio.run(mono.generate_thought(memory, None, Flaky(), "m"))
    second = asyncio.run(mono.generate_thought(memory, None, Flaky(), "m"))
    assert first is None and second and "bug" in second


def test_the_digest_may_only_quote_what_was_said():
    """DECISIONS Q4: the digest is posted as her observation of real people."""
    from utils.core.background_tasks import CoreTaskManager as M
    conv = "Ekco: i think the rover’s   wheels are toast\nStarkind: Nala knocked the plant over again"
    assert M._unverified_quotes('Ekco said "I think the rover\'s wheels are toast."', conv) == []
    assert M._unverified_quotes('Starkind said "Nala is a menace".', conv) == ["Nala is a menace"]
    assert M._unverified_quotes("They were on about rovers and cats.", conv) == []

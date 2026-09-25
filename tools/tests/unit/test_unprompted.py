"""The one system every unprompted post goes through: gate, label, send, cross-post."""
import asyncio
import random
import time
import types
from collections import deque

import pytest

from utils.core import unprompted as up

LABEL = "🧵 **Train of thought:**"


@pytest.fixture
def cfg(monkeypatch):
    """A config the test controls; anything unset falls back to the module default."""
    values = {"bluesky.enabled": True}

    class Cfg:
        max_memory_messages = 10

        def get(self, key, default=None):
            return values.get(key, default)

    monkeypatch.setattr(up, "_config", lambda: Cfg())
    up._last_label.clear()
    return values


def _state(**kw):
    s = types.SimpleNamespace(unprompted_date="", unprompted_count=0,
                              unprompted_last_sent=0.0, channel_memory={})
    s.save = lambda: None
    s.__dict__.update(kw)
    return s


# ── compose ────────────────────────────────────────────────────────────────
def test_a_single_post_is_label_then_text():
    assert up.compose("💬 **Passing thought:**", "hm.") == ["💬 **Passing thought:** hm."]


def test_a_thread_is_one_message_not_a_code_block_per_post():
    out = up.compose(LABEL, posts=["first.", "second.", "third."])
    assert out == [f"{LABEL} first.\n\nsecond.\n\nthird."]
    assert "```" not in out[0] and "[Thread" not in out[0]


def test_a_long_thread_splits_between_posts():
    out = up.compose(LABEL, posts=["a" * 900, "b" * 900, "c" * 900])
    assert all(len(m) <= 2000 for m in out)
    assert out[0].startswith(LABEL) and not out[1].startswith(LABEL)
    assert "".join(out).count("a" * 900) == 1


def test_a_post_longer_than_a_message_is_still_sent_whole():
    out = up.compose("", "word " * 600)
    assert all(len(m) <= 2000 for m in out)
    assert " ".join(m.strip() for m in out).split() == ("word " * 600).split()


def test_no_label_means_no_leading_space():
    assert up.compose("", "hey starkind.") == ["hey starkind."]


# ── labels ─────────────────────────────────────────────────────────────────
def test_render():
    assert up.render("🪡 Unspooling") == "🪡 **Unspooling:**"
    assert up.render("Plain") == "**Plain:**"
    assert up.render("") == ""


def test_an_observation_is_always_an_observation(cfg):
    for _ in range(20):
        assert up.pick_label("observation", "i used to think? what if? " * 50) == "💭 **Observation:**"


def test_an_absence_checkin_goes_out_unlabelled(cfg):
    assert up.pick_label("proactive", "hey, been a while.", source="absence") == ""


@pytest.mark.parametrize("kind, text, source, brief, expected", [
    ("proactive", "i used to think that was obvious. now i'm not so sure anymore.",
     "", "", "🪡 **Unspooling:**"),
    ("proactive", "hm.", "knowledge", "You recently read something related to: 'x'.",
     "🌀 **Down the rabbit hole:**"),
    ("proactive", "a thought.", "", "You recently changed your mind about 'x'.",
     "🪡 **Unspooling:**"),
    ("quip", "what if the whole thing is backwards? does anyone else see it? why do we?",
     "", "", "🦋 **Thinking out loud:**"),
])
def test_the_post_steers_the_label(cfg, kind, text, source, brief, expected):
    seen = [up.pick_label(kind, text, source=source, brief=brief, scope=str(i),
                          rng=random.Random(i)) for i in range(200)]
    assert seen.count(expected) > len(seen) / 2, (expected, set(seen))


def test_a_label_is_not_repeated_back_to_back(cfg):
    rng = random.Random(7)
    seen = [up.pick_label("quip", "hm.", scope="chan", rng=rng) for _ in range(300)]
    repeats = sum(a == b for a, b in zip(seen, seen[1:]))
    assert len(set(seen)) >= 3
    assert repeats < len(seen) * 0.35


def test_labels_only_come_from_the_kinds_own_list(cfg):
    allowed = {up.render(up.DEFAULT_LABELS[k]) for k in up.KIND_LABELS["quip"]}
    for i in range(200):
        assert up.pick_label("quip", "long " * 200, scope=str(i)) in allowed


def test_rotate_off_gives_the_home_label(cfg):
    cfg["unprompted.rotate"] = False
    assert up.pick_label("proactive", "i used to think…") == "☕ **Apropos of nothing:**"
    assert up.pick_label("thread", "x", posts=5) == "🧵 **Train of thought:**"


def test_a_retired_label_is_never_used(cfg):
    cfg["unprompted.labels.passing_thought"] = ""
    for i in range(200):
        assert up.pick_label("quip", "hm.", scope=str(i)) != "💬 **Passing thought:**"


def test_a_hand_set_legacy_prefix_is_still_honoured(cfg):
    cfg["quip.broadcast_prefix"] = "🎲 **Custom:**"
    assert up.pick_label("quip", "anything") == "🎲 **Custom:**"


# ── the gate ───────────────────────────────────────────────────────────────
def test_the_gate_is_shared_by_all_four_sources(cfg):
    cfg.update({"unprompted.max_per_day": 2, "unprompted.min_interval_minutes": 0})
    state = _state()
    now = time.time()
    up.record(state, now)
    up.record(state, now)
    for source in up.SOURCES:
        ok, why = up.gate(state, source, now)
        assert not ok and "daily limit 2/2" in why


def test_the_gap_is_shared_and_says_how_long_is_left(cfg):
    cfg.update({"unprompted.max_per_day": 0, "unprompted.min_interval_minutes": 60})
    state = _state()
    now = time.time()
    up.record(state, now)
    ok, why = up.gate(state, "observation", now + 600)
    assert not ok and "50 min left of the 60 min gap" in why
    assert up.gate(state, "observation", now + 3601)[0]


def test_a_new_day_resets_the_count(cfg):
    cfg.update({"unprompted.max_per_day": 1, "unprompted.min_interval_minutes": 0})
    state = _state(unprompted_date="2000-01-01", unprompted_count=99)
    assert up.gate(state, "quip")[0]


def test_switches(cfg):
    cfg["unprompted.sources.monologue"] = False
    assert not up.gate(_state(), "monologue")[0]
    assert up.gate(_state(), "quip")[0]
    cfg["unprompted.enabled"] = False
    assert not any(up.gate(_state(), s)[0] for s in up.SOURCES)


def test_posting_hours(cfg):
    from datetime import datetime
    cfg.update({"unprompted.respect_quiet_hours": True,
                "unprompted.quiet_hour_start": 22, "unprompted.quiet_hour_end": 6})
    assert up.within_hours(datetime(2026, 9, 22, 23, 0))
    assert up.within_hours(datetime(2026, 9, 22, 3, 0))
    assert not up.within_hours(datetime(2026, 9, 22, 12, 0))
    cfg["unprompted.respect_quiet_hours"] = False
    assert up.within_hours(datetime(2026, 9, 22, 12, 0))


# ── sending ────────────────────────────────────────────────────────────────
class _Channel:
    id = 42

    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


def _speak(monkeypatch, cfg, *, bluesky_on, manual=False, cross_post=True,
           posts=None, text="a thought.", state=None):
    calls = []

    async def fake_post(text):
        calls.append(("single", text))
        return True, "uri"

    async def fake_thread(chunks):
        calls.append(("thread", list(chunks)))
        return True, "uri"

    import utils.social.kaia_bluesky as bsky
    monkeypatch.setattr(bsky, "post_to_bluesky", fake_post)
    monkeypatch.setattr(bsky, "post_thread_to_bluesky", fake_thread)
    cfg["unprompted.bluesky.quip"] = bluesky_on
    cfg.update({"unprompted.max_per_day": 1, "unprompted.min_interval_minutes": 0})
    state = state or _state()
    ctx = types.SimpleNamespace(bot_state=state)
    channel = _Channel()
    result = asyncio.run(up.speak(ctx, channel, "quip", text, posts=posts,
                                  kind="thread" if posts else None,
                                  manual=manual, cross_post=cross_post))
    return result, channel, calls, state


def test_speak_sends_remembers_cross_posts_and_spends_the_allowance(monkeypatch, cfg):
    result, channel, calls, state = _speak(monkeypatch, cfg, bluesky_on=True)
    assert result.posted and result.bluesky is True
    assert channel.sent and channel.sent[0].endswith("a thought.")
    assert calls == [("single", "a thought.")]                 # no label on the feed
    assert list(state.channel_memory[42])[-1]["content"] == "a thought."
    assert state.unprompted_count == 1


def test_a_thread_goes_to_bluesky_as_a_thread(monkeypatch, cfg):
    result, _, calls, _ = _speak(monkeypatch, cfg, bluesky_on=True,
                                 posts=["one.", "two.", "three."])
    assert calls == [("thread", ["one.", "two.", "three."])]


def test_a_source_off_the_bluesky_list_stays_on_discord(monkeypatch, cfg):
    result, channel, calls, _ = _speak(monkeypatch, cfg, bluesky_on=False)
    assert result.posted and channel.sent and calls == [] and result.bluesky is None


def test_a_checkin_is_never_cross_posted(monkeypatch, cfg):
    _, _, calls, _ = _speak(monkeypatch, cfg, bluesky_on=True, cross_post=False)
    assert calls == []


def test_a_closed_gate_sends_nothing(monkeypatch, cfg):
    full = _state(unprompted_date=time.strftime("%Y-%m-%d"), unprompted_count=1)
    result, channel, calls, _ = _speak(monkeypatch, cfg, bluesky_on=True, state=full)
    assert not result.posted and "daily limit" in result.reason
    assert channel.sent == [] and calls == []


def test_a_manual_quip_skips_the_gate_and_spends_nothing(monkeypatch, cfg):
    full = _state(unprompted_date=time.strftime("%Y-%m-%d"), unprompted_count=1)
    result, channel, _, state = _speak(monkeypatch, cfg, bluesky_on=True,
                                       manual=True, state=full)
    assert result.posted and channel.sent and state.unprompted_count == 1


def test_descriptive_labels_are_only_worn_when_earned(cfg):
    """'Unspooling' on a post that questions nothing would stop meaning anything."""
    descriptive = {up.render(up.DEFAULT_LABELS[k]) for k in
                   ("unspooling", "rabbit_hole", "long_thought", "train_of_thought")}
    for kind in ("quip", "proactive", "monologue"):
        for i in range(300):
            label = up.pick_label(kind, "the servers were quiet today.", scope=f"{kind}{i}",
                                  rng=random.Random(i))
            assert label not in descriptive, (kind, label)


def test_a_mocked_config_can_never_reach_a_public_feed(monkeypatch):
    """A MagicMock config answers every key with something truthy. A test that
    mocked the config reached the real Bluesky posting function that way; a
    cross-post needs a literal `true`."""
    from unittest.mock import MagicMock
    monkeypatch.setattr(up, "_config", lambda: MagicMock())
    assert not up.cross_posts("quip")
    assert not up.cross_posts_x("quip")
    assert up.pick_label("quip", "x", rng=random.Random(1)).startswith(("💬", "☕", "🦋"))


def test_an_afterthought_wears_its_own_label():
    from utils.core import unprompted
    assert unprompted.compose(unprompted.pick_label("afterthought"), "actually, one more thing.") == [
        "🕰️ **Afterthought:** actually, one more thing."]


def test_the_overnight_log_is_posted_but_not_kept_as_one_of_her_turns(monkeypatch, cfg):
    """Held in channel history, its readings were copied into later replies."""
    cfg.update({"unprompted.max_per_day": 1, "unprompted.min_interval_minutes": 0})
    state = _state()
    channel = _Channel()
    result = asyncio.run(up.speak(types.SimpleNamespace(bot_state=state), channel, "overnight",
                                  "the planetary k index is 4.3."))
    assert result.posted and channel.sent
    assert not state.channel_memory.get(42)

"""When she says she is flagging something for review, it is flagged."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.core import review_flags as rf


@pytest.mark.parametrize("reply", [
    "a lapse in retrieval. it's on lateralus. i’m flagging that for review. again.",
    "i do not have the information. i am logging this incident for review.",
    "i'll flag it for ekco's review.",
    "It has been flagged for review.",
    "a deficiency i am now actively flagging for review.",
])
def test_her_flagging_phrasings_are_claims(reply):
    assert rf.find_claim(reply)


@pytest.mark.parametrize("reply", [
    "entries exceeding that threshold would be flagged for review and removed.",
    "do you wish me to log the incident for ekco’s awareness?",
    "if presented with alternative directives, i would likely flag them for review.",
    "the reported incident with the canadian man is noted.",
    "the cron job logs to /var/log and nobody reviews it.",
])
def test_describing_or_offering_a_flag_is_not_one(reply):
    assert rf.find_claim(reply) is None


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "review_flags.jsonl"
    monkeypatch.setattr(rf, "FLAGS", str(path))
    return path


def _record(reply, now=1_792_000_000.0):
    return rf.record(reply, author="Cecily", author_id=14, own_words="what album is the outer lobotomy on",
                     channel_name="general", channel_id=99, jump_url="https://discord.com/channels/1/99/5", now=now)


def test_a_claimed_flag_is_recorded_with_what_was_said(store):
    row = _record("a lapse in retrieval. i’m flagging that for review.")
    saved = [json.loads(x) for x in store.read_text().splitlines()]
    assert saved == [row]
    assert row["claim"] == "i’m flagging that for review." and row["said_to_her"].startswith("what album")
    assert row["post"] and row["status"] == "open"
    assert _record("nothing claimed here.") is None


def test_her_own_notes_are_recorded_not_posted_and_posts_are_capped(store):
    assert _record("i will log it for future analysis.")["post"] is False
    posted = [_record(f"point {i}. i'm flagging that for review.", now=1_792_000_000.0 + i)["post"]
              for i in range(rf.MAX_POSTS_PER_DAY + 2)]
    assert posted.count(True) == rf.MAX_POSTS_PER_DAY


def test_a_flag_is_posted_to_kaia_opolis(store, monkeypatch):
    import discord
    channel = SimpleNamespace(name="kaia-opolis", send=AsyncMock())
    monkeypatch.setattr(discord.utils, "get", lambda channels, name: channel if name == "kaia-opolis" else None)
    bot = MagicMock()
    row = _record("i am logging this incident for review.")
    assert asyncio.run(rf.notify(bot, row)) is True
    embed = channel.send.call_args.kwargs["embed"]
    assert "logging this incident" in embed.description
    assert any("outer lobotomy" in f.value for f in embed.fields)

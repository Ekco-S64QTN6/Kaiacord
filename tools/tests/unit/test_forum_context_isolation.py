"""Three ways a forum draft picked up context that was not its own.

All reported by the operator on 2026-09-18: posts that "inject unrelated context
from previous posts by different people", forum output "lower quality than the
output she gives in Discord", and a rejected draft whose topic kept coming back.
"""
import pytest

from utils.infrastructure.system.external_mention import conversation_channel_id
from utils.social import forum_drafting
from utils.social.forum_participation import PostLedger


def test_seeded_history_lands_on_the_key_the_processor_reads():
    """The seed was written under str(id) and read back under int(id).

    `bot_state.channel_memory` is documented as int-keyed and `bot_state.load()`
    casts to int, so the string keys were also discarded on every restart. The
    net effect was that no forum draft ever had conversation history, which is
    the whole reason her forum voice read as boilerplate next to her Discord one.
    """
    from utils.infrastructure.system.bot_state import bot_state

    thread_id = 990443378   # not a real thread: no scraped copy on disk to merge
    posts = [{"post_number": i, "author": a, "content": c, "post_id": 1000 + i,
              "own_text": c}
             for i, (a, c) in enumerate(
                 [("Ekco", "the scraper keeps timing out on page three"),
                  ("BradZax", "mine has been fine all week"),
                  ("Kaia", "sounds like a rate limit rather than a fault")], start=1)]

    key = conversation_channel_id(forum_drafting.PLATFORM, thread_id)
    bot_state.channel_memory.pop(key, None)
    bot_state.channel_memory.pop(str(key), None)

    n = forum_drafting.seed_thread_history(None, thread_id, posts, "Kaia")
    assert n == 3

    assert isinstance(key, int)
    assert key in bot_state.channel_memory, "seeded under a key nothing reads"
    assert str(key) not in bot_state.channel_memory, "still writing a string key"

    turns = list(bot_state.channel_memory[key])
    assert turns[0]["content"].startswith("Ekco: ")
    assert turns[-1]["role"] == "assistant", "her own posts must be assistant turns"
    assert all(t["external"] == "vbulletin" for t in turns)
    bot_state.channel_memory.pop(key, None)


def test_antecedent_comes_from_what_they_quoted_not_from_whoever_posted_before():
    """Adjacency is not a reply relationship on a 177-post thread."""
    target = {
        "author": "Ekco",
        "post_id": 3801037,
        "own_text": "that matches what i saw on the test box",
        "content": ("Quote:\nOriginally Posted by BradZax\n"
                    "the scraper only fails when the thread is over 100 pages\n"
                    "that matches what i saw on the test box"),
    }
    who, quoted = forum_drafting.quoted_context(target)
    assert who == "BradZax"
    assert "over 100 pages" in quoted
    assert "that matches what i saw" not in quoted, "his own words leaked into the quote"


def test_a_post_quoting_nobody_has_no_antecedent():
    target = {"author": "Ekco", "post_id": 1,
              "own_text": "still broken after the reinstall",
              "content": "still broken after the reinstall"}
    who, quoted = forum_drafting.quoted_context(target)
    assert (who, quoted) == ("", ""), \
        "an unquoted post must not borrow the previous poster's subject"


def test_a_rejected_draft_is_remembered_and_fails_the_novelty_check(tmp_path):
    ledger = PostLedger(path=tmp_path / "ledger.json")
    body = ("the usual culprit here is the loader, not the disk. worth checking "
            "the boot order before you reinstall anything.")
    ledger.note_skip(443378, 3801037, body=body)

    assert ledger.rejected_bodies() == [body]
    # Reloaded from disk, because the next draft constructs a fresh ledger.
    assert PostLedger(path=tmp_path / "ledger.json").rejected_bodies() == [body]


def test_rejected_bodies_are_bounded_per_thread(tmp_path):
    ledger = PostLedger(path=tmp_path / "ledger.json")
    for i in range(9):
        ledger.note_skip(443378, 3801037 + i, body=f"draft number {i} about the loader")
    assert len(ledger.rejected_bodies()) == 5, "unbounded growth in a file read on every construction"


def test_note_skip_without_a_body_still_retires_the_post(tmp_path):
    ledger = PostLedger(path=tmp_path / "ledger.json")
    ledger.note_skip(443378, 3801037)
    assert ledger.already_tried(443378, 3801037)
    assert ledger.rejected_bodies() == []


def test_proactive_topics_ignore_forum_turns():
    """A Discord opener must not be a follow-up to a stranger's P1999 post.

    `channel_memory` is replaced wholesale for the duration: the selection is a
    weighted random draw, so leaving the process's real history in place makes
    the assertion depend on which message the draw happened to land on.
    """
    import time
    from utils.infrastructure.system.bot_state import bot_state
    from utils.core.kaia_proactive import ProactiveEngine

    forum_key = conversation_channel_id("vbulletin", 999001)
    saved = bot_state.channel_memory
    bot_state.channel_memory = {forum_key: [{
        "role": "user", "timestamp": time.time(), "external": "vbulletin",
        "content": ("BradZax: the velious armor quest chain is still bugged on the "
                    "classic shard and nobody from the staff has said anything about it"),
    }]}
    try:
        engine = ProactiveEngine.__new__(ProactiveEngine)
        assert engine._get_conversation_followup(bot_state) is None, \
            "a forum post was offered as the subject of a Discord opener"

        # And the same turn without the tag is still usable, so the filter is
        # keying on provenance rather than quietly disabling the feature.
        bot_state.channel_memory[forum_key][0].pop("external")
        assert engine._get_conversation_followup(bot_state) is not None
    finally:
        bot_state.channel_memory = saved

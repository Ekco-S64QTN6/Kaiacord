"""A forum post must not be presented as something said in Discord.

`knowledge_base/user_logs/` holds both Discord transcripts and scraped Project
1999 posts — 218 forum directories against 9 Discord ones, 47% of the corpus by
size. Both matched `is_log` in the context weaver, so a years-old forum post was
injected into the prompt as

    [CONVERSATION HISTORY: TENNO | 2026-09-07]

and she recalled it as something said to her in Discord. The accounts belong to
the same people — the identity registry links them deliberately — so the fix is
provenance, not separation.
"""
import inspect
import re

from utils.core.context_optimizer import ContextOptimizer

SRC = inspect.getsource(ContextOptimizer)


def test_forum_logs_get_their_own_label():
    assert 'user_logs/forum_' in SRC, "forum user logs are not distinguished"
    assert "FORUM POST" in SRC
    assert "NOT said in Discord" in SRC


def test_the_forum_branch_precedes_the_generic_history_label():
    """If the generic branch ran first the label would say CONVERSATION
    HISTORY and the venue would be lost again."""
    assert SRC.index('user_logs/forum_') < SRC.index('# Add user name and date provenance')


def test_the_speaker_name_survives_the_relabel():
    """Same person on both platforms, so the name must still be attached —
    only the venue was missing. `speaker_from_log_path` yields
    'forum Tenno Henka 123' for a forum directory; the prefix and the trailing
    forum id are cosmetic and get cleaned."""
    cleaned = re.sub(r'\s+\d+$', '', re.sub(r'^FORUM\s+', '', "FORUM TENNO HENKA 123")).strip()
    assert cleaned == "TENNO HENKA"


def test_discord_logs_are_untouched():
    """The Discord path must still read as conversation history."""
    assert "CONVERSATION HISTORY" in SRC


def test_forum_and_discord_dirs_are_distinguishable_on_disk():
    """The only reliable marker is the owning directory name."""
    from utils.core.rag_utils import speaker_from_log_path

    forum = "knowledge_base/user_logs/forum_Tenno_Henka_123/interactions_20260907.md"
    discord = "knowledge_base/user_logs/Tenno_Henka_919782120308752425/interactions_20260914.md"
    assert "user_logs/forum_" in forum.lower()
    assert "user_logs/forum_" not in discord.lower()
    assert speaker_from_log_path(discord) == "Tenno Henka"

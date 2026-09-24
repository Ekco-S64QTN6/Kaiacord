"""Heuristics that judge the speaker read their words, not the enrichment.

`sanitized_content` carries the quoted post and any fetched page. Read by a
heuristic, that text is attributed to the person: an article about a war
lowered their relationship valence, and "I'm going to..." in a linked page was
saved as their plan and asked about when they came back (CLAUDE.md §5).
"""
import inspect
import re

from utils.core.message_context import MessageContext
from utils.core.message_processor import MessageProcessor


def test_own_words_drops_quote_and_page():
    ctx = MessageContext(message=None, sanitized_content=(
        "[REPLYING_TO]\nLune: i'm going to quit\n\n[USER_MESSAGE]\nkaia look\n\n"
        "[LINKED_WEB_CONTENT]\nthe system prompt of every model"))
    assert ctx.own_words == "kaia look"


# (fragment that must read own words, what it decides)
MUST_READ_OWN = [
    ("estimate_sentiment(_own)", "relationship valence"),
    ("summary = _own[:120]", "relationship event summary"),
    ("message_length=len(_own)", "emotional arc"),
    ("_content_lower = _own.lower()", "open loops"),
    ("update_user_state(ctx.author_id, ctx.own_words)", "theory of mind"),
    ("_CLAIM_PATTERNS.search(ctx.own_words)", "false-memory claim guard"),
    ("_SD_PATTERNS.search(ctx.own_words)", "self-disclosure note"),
    ("_is_kb_query(ctx.own_words)", "knowledge-base constraint"),
    ("resolve_time_queries(ctx.own_words", "time facts"),
]


def test_speaker_heuristics_read_own_words():
    src = inspect.getsource(MessageProcessor)
    missing = [why for frag, why in MUST_READ_OWN if frag not in src]
    assert not missing, missing
    for fn in ("estimate_sentiment", "_CLAIM_PATTERNS.search", "_SD_PATTERNS.search",
               "_is_observational_query", "_extract_recap_hours", "_is_kb_query"):
        assert not re.search(rf"{re.escape(fn)}\(ctx\.sanitized_content", src), fn

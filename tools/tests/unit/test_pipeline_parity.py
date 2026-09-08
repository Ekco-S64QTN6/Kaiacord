"""The forum must use the Discord pipeline, unmodified.

Every forum defect this project has had traced to something that made the forum
path different: a FORUM_POST_GUIDANCE block telling it to "say one thing", a
"write at least 3-4 complete sentences" instruction, an addressee anchor Discord
got and the forum was excluded from, a fallback Discord would not accept, a
larger sanitiser cap, and a message shape that sent the *thread* as the user's
message with the person's actual post demoted to background.

The operator's requirement: "DISCORD OUTPUT AND FORUM OUTPUT SHOULD BE THE SAME,
HOWEVER YOU HAVE TO ACHIEVE THAT." These tests are how that is kept true.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROC = Path("utils/core/message_processor.py")


def _ctx(platform):
    from utils.core.message_context import MessageContext

    author = MagicMock()
    author.display_name = "Ekco"
    author.name = "Ekco"
    author.id = 177011971818782721
    channel = MagicMock()
    channel.id = 1
    msg = MagicMock()
    msg.platform = platform
    msg.author = author
    msg.channel = channel
    msg.content = "reply to this kaia, test test hello hello"
    msg.attachments = []

    ctx = MessageContext(
        message=msg,
        sanitized_content="reply to this kaia, test test hello hello",
        is_social=(platform != "discord"),
        is_mention=True, is_dm=False,
        parent_context="datacenters use 2 billion gallons a year",
        root_context="THREAD TITLE: The absolute state of AI results.",
        start_time=0.0,
    )
    ctx.category = "general"
    return ctx


def _messages(platform):
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config

    p = MessageProcessor.__new__(MessageProcessor)
    p.config = config
    return p._construct_messages(
        _ctx(platform), {"persona": "PERSONA", "rag": "RAGCTX", "history": []})


def test_the_same_input_produces_the_same_prompt():
    """The whole requirement, in one assertion."""
    assert _messages("discord") == _messages("vbulletin")


def test_the_system_prompt_is_byte_identical():
    d, f = _messages("discord"), _messages("vbulletin")
    assert d[0]["content"] == f[0]["content"]


def test_the_user_turn_is_byte_identical():
    d, f = _messages("discord"), _messages("vbulletin")
    assert d[-1]["content"] == f[-1]["content"]


def test_prompt_assembly_has_no_platform_conditionals():
    """`is_social` may remain: it skips guild/bot-author checks a MockMessage
    cannot satisfy, and touches nothing about generation."""
    import re
    src = PROC.read_text(encoding="utf-8")
    conds = [l.strip() for l in src.splitlines()
             if re.search(r"platform\s*[=!]=", l) and not l.strip().startswith("#")]
    assert conds == ["is_social = platform != 'discord'"], conds


def test_no_forum_specific_instructions_survive():
    src = PROC.read_text(encoding="utf-8")
    for gone in ("Write at least 3-4 complete sentences",
                 "You are posting on the Project 1999 forum",
                 "forum_context_block",
                 "and not is_vbulletin",
                 "is_vbulletin and best_fallback_response"):
        assert gone not in src, f"forum special-case still present: {gone}"


def test_the_guidance_constant_is_gone():
    import utils.social.forum_participation as fp
    assert not hasattr(fp, "FORUM_POST_GUIDANCE")


def test_one_sanitiser_cap_for_every_platform():
    """The forum needed a larger cap only while the whole thread was being sent
    as the user's message."""
    src = PROC.read_text(encoding="utf-8")
    assert "max_length=8000" not in src
    assert "sanitize_prompt(main_content)" in src


def test_rag_is_called_identically():
    """No platform argument reaches retrieval, so the same query with the same
    parameters is issued on both paths."""
    import inspect
    from utils.core.kaia_rag_query import RAGQueryMixin

    params = inspect.signature(RAGQueryMixin.retrieve).parameters
    assert "platform" not in params

    src = PROC.read_text(encoding="utf-8")
    call = src[src.index("tasks['rag'] = asyncio.create_task(self.run_rag("):][:600]
    assert "platform" not in call, "retrieval is being told which platform this is"


def test_drafting_asks_the_pipeline_once_and_adds_nothing():
    import inspect
    from utils.social.forum_drafting import draft_forum_reply

    src = inspect.getsource(draft_forum_reply)
    assert src.count("process_external_mention(") == 1
    for added in ("for attempt in range", "too thin to post",
                  "MIN_DRAFT_CHARS", "SYSTEM INSTRUCTION"):
        assert added not in src, f"still adding something: {added}"


def test_the_forum_message_shape_matches_a_discord_reply():
    """[ORIGINAL_POST] / [REPLYING_TO] / [USER_MESSAGE] is what Discord sends
    for a reply. root_context is injected only when parent_context is set, so
    omitting [REPLYING_TO] silently discarded the entire thread."""
    import inspect
    from utils.social.forum_drafting import draft_forum_reply

    src = inspect.getsource(draft_forum_reply)
    for marker in ("[ORIGINAL_POST]", "[REPLYING_TO]", "[USER_MESSAGE]"):
        assert marker in src, f"{marker} not sent"

    proc = PROC.read_text(encoding="utf-8")
    i = proc.index("if ctx.parent_context:")
    assert "root_context" in proc[i:i + 400], "root is gated behind parent; both must be sent"


# ── The inputs must match too, not only the assembly ─────────────────

def test_a_forum_thread_becomes_conversation_history():
    """The earlier parity tests passed `history: []` to both sides, so they
    proved assembly is identical *given identical inputs* — and the inputs were
    not identical. Discord draws on a channel's accumulated turns; a forum
    thread maps to a channel id nothing ever writes to, so history was empty and
    she answered every post cold. That is most of what "boilerplate one
    sentence" was."""
    from utils.infrastructure.system.bot_state import bot_state
    from utils.infrastructure.system.external_mention import conversation_channel_id
    from utils.social.forum_drafting import seed_thread_history

    posts = [
        {"post_id": 1, "author": "BradZax", "content": "datacenters use 2bn gallons"},
        {"post_id": 2, "author": "Kaia", "content": "that figure needs a denominator."},
        {"post_id": 3, "author": "OriginalContentGuy", "content": "almonds use more"},
    ]
    # A thread id with no local copy, so this measures the live posts only —
    # the merge with the scraped copy is covered separately.
    n = seed_thread_history(None, 88888888, posts, "Kaia")
    assert n == 3

    turns = bot_state.channel_memory[str(conversation_channel_id("vbulletin", 88888888))]
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    # Her own posts are hers; everyone else is named, exactly as Discord stores it.
    assert turns[1]["content"] == "that figure needs a denominator."
    assert turns[0]["content"].startswith("BradZax: ")
    assert all("timestamp" in t for t in turns)


def test_thread_history_is_bounded():
    from utils.social.forum_drafting import seed_thread_history, MAX_THREAD_HISTORY_TURNS
    from utils.infrastructure.system.bot_state import bot_state
    from utils.infrastructure.system.external_mention import conversation_channel_id

    posts = [{"post_id": i, "author": f"u{i}", "content": f"post {i}"} for i in range(50)]
    seed_thread_history(None, 999, posts, "Kaia")
    turns = bot_state.channel_memory[str(conversation_channel_id("vbulletin", 999))]
    assert len(turns) == MAX_THREAD_HISTORY_TURNS
    assert turns[-1]["content"].endswith("post 49"), "keeps the most recent"


def test_the_history_channel_matches_the_one_the_pipeline_reads():
    """Seeding the wrong channel id would be silently useless."""
    from utils.infrastructure.system.external_mention import conversation_channel_id
    import inspect
    from utils.social.forum_drafting import seed_thread_history, draft_forum_reply

    assert "conversation_channel_id(PLATFORM, thread_id)" in inspect.getsource(seed_thread_history)
    assert "conversation_key=thread_id" in inspect.getsource(draft_forum_reply)
    assert conversation_channel_id("vbulletin", 1) != conversation_channel_id("vbulletin", 2)


def test_the_locally_scraped_thread_is_used_as_context():
    """The live scrape fetches ten posts; the scraper keeps up to 200 on disk
    and they were going entirely unused. `forum_posts` is excluded from the RAG
    index so strangers' claims cannot surface as fact in unrelated
    conversations — that is about *global retrieval*. Reading the thread she is
    about to post in, as context for that post, is scoped."""
    from utils.social.forum_drafting import load_scraped_thread

    posts = load_scraped_thread(443378)
    if not posts:
        pytest.skip("no scraped copy of that thread on disk")
    assert len(posts) > 10, "should reach further back than a live scrape"
    assert all(p.get("author") and p.get("content") for p in posts)
    assert all(isinstance(p.get("post_number"), int) for p in posts)


def test_a_missing_or_unparsable_thread_file_is_harmless():
    from utils.social.forum_drafting import load_scraped_thread
    assert load_scraped_thread(99999999) == []
    assert load_scraped_thread("not-a-number") == []


def test_quote_scaffolding_is_stripped_from_history():
    """The scraped copy stores quote boxes flattened, so a reply begins
    "Quote: / Originally Posted by / <name>". That is markup, not content."""
    from utils.social.forum_drafting import _readable

    out = _readable("Quote:\nOriginally Posted by\nBradZax\nlol im not exagurating\nfair point")
    assert "Quote:" not in out and "Originally Posted by" not in out
    assert "lol im not exagurating" in out and "fair point" in out


def test_the_local_copy_only_supplements_the_live_scrape():
    """The live posts are the current state and must remain the tail."""
    import inspect
    from utils.social.forum_drafting import seed_thread_history
    src = inspect.getsource(seed_thread_history)
    assert "older + list(earlier_posts)" in src
    assert "len(scraped) > len(earlier_posts)" in src

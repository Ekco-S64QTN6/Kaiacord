"""Turning a forum thread into a draft, through the same pipeline as Discord.

There used to be two implementations. The auto-reply path called
`process_external_mention`, which is the real pipeline — RAG, memory, the
dual-temperature split, the full post-generation safety stack. The auto-post
task assembled its own persona-plus-thread-context prompt, called
`ollama_client.chat` directly at a hardcoded temperature 0.8, and then
re-applied the filter stack by hand. That is why her forum voice drifted from
her Discord voice: it was not the same code, and only one of the two had her
memory.

This module is the single path. It builds the content in the format
`message_processor._construct_messages` already expects for `platform=
"vbulletin"`, hands it to the pipeline, and applies the two things that are
specific to posting somewhere public: a repetition check against her recent
posts, and BBCode quoting.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.social.forum_participation import PostLedger, looks_repetitive

# vBulletin's own platform tag. The processor keys its forum-specific prompt
# assembly off this exact string; `forum_tasks` used to pass "forum", which
# silently took the ordinary Discord path and lost the thread context entirely.
PLATFORM = "vbulletin"

# How much of a thread becomes conversation history. Discord's channel memory is
# bounded the same way; the context optimizer trims further to fit its budget.
MAX_THREAD_HISTORY_TURNS = 12

# What message_processor returns when it cannot produce a response. These are
# fine in Discord, where they read as her being stuck for a moment. On a public
# forum they are a bot visibly malfunctioning.
GENERATION_FAILURES = (
    "i'm drawing a blank on that one",
    "the data's a bit scrambled",
    "knowledge base is busy",
    "not enough gpu memory",
    "that took too long",
    "something went wrong",
)


def is_generation_failure(text: str) -> bool:
    low = (text or "").lower()
    return any(f in low for f in GENERATION_FAILURES)


def _as_dict(post: Any) -> dict:
    return post if isinstance(post, dict) else post.to_dict()


def format_thread_context(title: str, posts: list, limit: int = 5000) -> str:
    lines = []
    for p in posts:
        d = _as_dict(p)
        lines.append(f"#{d.get('post_number', '?')} {d.get('author', 'Unknown')}: "
                     f"{d.get('content', '')}")
    body = "\n---\n".join(lines)
    if len(body) > limit:
        body = "...\n" + body[-limit:]
    return f"THREAD TITLE: {title}\n\nTHREAD CONTEXT:\n{body}"


# vBulletin flattens a quoted post into the body text as a "Quote:" label
# followed by "Originally Posted by <name>". Quoting a post that itself contains
# a quote would copy that text into her quote box under the wrong author's name,
# which is what the Reply With Quote button strips for you.
_NESTED_QUOTE = re.compile(r'^\s*(quote:|originally posted by\b)', re.IGNORECASE)


def own_words(post, limit: int = 700) -> str:
    """A poster's own text, without whatever they were quoting.

    Prefers `own_text`, which the scraper extracts by removing the quote nodes
    while the HTML structure is still present. The line-scanning fallback below
    is only for posts that predate that field.

    The fallback used to keep everything *before* the first "Quote:" marker and,
    finding nothing there, fall back to the entire content. On a post whose
    quote box comes first — quote, then the poster's one-line reply — that
    returned the whole thing, so Kaia quoted BradZax's words inside a box
    attributed to Jimjam. A flattened post has no reliable boundary; that is
    why the real fix is at scrape time.
    """
    if not isinstance(post, str):
        explicit = (post or {}).get("own_text") if hasattr(post, "get") else None
        if explicit:
            return explicit[:limit].rsplit(" ", 1)[0] + "..." if len(explicit) > limit else explicit
        content = (post or {}).get("content", "") if hasattr(post, "get") else ""
    else:
        content = post

    lines, out = (content or "").split("\n"), []
    for line in lines:
        if _NESTED_QUOTE.match(line):
            break
        out.append(line)
    text = "\n".join(out).strip()
    if not text:
        # A post that is nothing but a quote gives us nothing to quote back.
        # Returning the whole thing would attribute someone else's words to
        # this poster, so return nothing and let the caller skip the quote.
        return ""
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return text


def quoted_context(post) -> tuple[str, str]:
    """What this post was actually replying to: (author, text).

    vBulletin flattens a quote box into the body as "Originally Posted by <name>"
    followed by the quoted words, and `own_text` is the same post with the quote
    nodes removed. The difference between them is therefore exactly the material
    this person chose to answer — which is the only honest source for
    `[REPLYING_TO]`.

    Returns ("", "") when the post quotes nobody. That is the common case and it
    matters that it is distinguishable: the caller previously fell back to the
    chronologically previous post in the thread, which on a busy thread is a
    different person talking about something else. Kaia then answered Ekco while
    holding BradZax's unrelated argument as "what Ekco was responding to", and
    the post came out about the wrong subject. On a forum, unlike a chat channel,
    adjacency is not a reply relationship.
    """
    d = _as_dict(post) if not isinstance(post, str) else {}
    content = (d.get("content") or "").strip()
    own = (d.get("own_text") or "").strip()
    if not content:
        return "", ""

    m = re.search(r"originally posted by\s+(.+)", content, re.IGNORECASE)
    author = m.group(1).split("\n")[0].strip() if m else ""

    # The quoted block is whatever the poster's own words are not. Without
    # `own_text` (posts scraped before it existed) there is no reliable boundary,
    # and guessing one is what attributed the wrong words to the wrong person.
    if not own or own == content:
        return "", ""
    quoted = content
    if own and own in quoted:
        quoted = quoted.replace(own, " ")
    quoted = _readable(quoted)
    quoted = re.sub(r"^\s*" + re.escape(author) + r"\s*", "", quoted).strip() if author else quoted
    return author, quoted[:700]


def pick_quote_target(posts: list, username: str, force: bool = False) -> Optional[dict]:
    """The post she is replying to — the one the Reply button would quote.

    This used to be a 40% coin flip on whether to quote at all, on the theory
    that quoting every time is as much of a tell as never quoting. That was
    wrong about how forums read: a quote box is how you say *who you are
    talking to*. Her first real post lost the flip and landed in a 929-post
    thread as a bare "yeah, that's good to hear" with no visible referent, and
    the operator could not tell whether she was answering him or the person
    above him. On P99, quoting is the normal reply chain; not quoting is the
    exception that needs a reason.
    """
    others = [p for p in posts
              if _as_dict(p).get('author', '').lower() != (username or '').lower()]
    return _as_dict(others[-1]) if others else None


SCRAPED_THREADS = Path("./knowledge_base/forum_posts")


def load_scraped_thread(thread_id: int) -> list[dict]:
    """The locally scraped copy of a thread, as post dicts.

    The live scrape fetches only the last ten posts. The scraper already keeps
    a fuller copy on disk — 200 posts for the thread she has been posting in —
    and it was going unused: `forum_posts` is deliberately excluded from the RAG
    index (kaia_rag_indexer.py:750) because indexing strangers' claims would let
    them surface as grounded fact in unrelated conversations.

    That exclusion is about *global retrieval*. Reading the thread she is about
    to post in, as context for that post, is scoped and is the whole point of
    keeping the copy.
    """
    try:
        files = list(SCRAPED_THREADS.glob(f"thread_{int(thread_id)}_*.md"))
    except (OSError, TypeError, ValueError):
        return []
    if not files:
        return []

    try:
        text = files[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    posts, header = [], re.compile(r"^## Post #(\d+) by (.+)$")
    current, body = None, []
    for line in text.splitlines():
        m = header.match(line)
        if m:
            if current:
                current["content"] = "\n".join(body).strip()
                posts.append(current)
            current, body = {"post_number": int(m.group(1)),
                             "author": m.group(2).strip(),
                             "post_id": None}, []
            continue
        if current is None:
            continue
        if line.strip() in ("---", "") or line.startswith("*"):
            continue
        body.append(line)
    if current:
        current["content"] = "\n".join(body).strip()
        posts.append(current)

    return [p for p in posts if p.get("content")]


def _readable(content: str) -> str:
    """A quoted post flattened for history, without the quote scaffolding.

    The scraped copy stores vBulletin quote boxes flattened, so a post that
    replies to someone begins "Quote: / Originally Posted by / <name>" before
    any of its own text. own_words() returns nothing for that shape by design —
    it exists to keep other people's words out of a *quote box* — but for
    history the quoted text is legitimate context. Only the scaffolding goes.
    """
    keep = []
    for line in (content or "").split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in ("quote:", "code:") or \
                stripped.lower().startswith("originally posted by"):
            continue
        keep.append(stripped)
    return "\n".join(keep).strip()


def seed_thread_history(ctx, thread_id: int, earlier_posts: list, username: str) -> int:
    """Load a thread's earlier posts into channel memory as conversation turns.

    Kaia's own posts become `assistant` turns and everyone else's become `user`
    turns prefixed with the poster's name, which is exactly how Discord stores
    a channel's recent messages. Returns the number of turns seeded.
    """
    try:
        from utils.infrastructure.system.bot_state import bot_state
        from utils.infrastructure.system.external_mention import conversation_channel_id
    except Exception:
        return 0

    # An int, because that is what `channel_memory` is keyed by. This was
    # `str(...)`, and `MessageProcessor` reads `bot_state.channel_memory[
    # ctx.channel_id]` where `ctx.channel_id` comes off the mock channel as an
    # int — so every thread was seeded under "222746109" and read back under
    # 222746109, and the read missed. `bot_state.load()` states the contract
    # explicitly ("channel_memory uses int keys") and casts on load, which also
    # meant the orphaned string keys were silently dropped at every restart.
    #
    # The effect was that the work this module exists to do never happened: the
    # log said "seeded 12 thread posts as conversation history" on every draft
    # and `optimize_context` received an empty history on every draft. That is
    # the whole of "her forum posts read worse than her Discord replies" — the
    # docstring below already names no-conversation-to-be-in-the-middle-of as
    # the cause of boilerplate, and the fix had been written but never connected.
    channel_id = conversation_channel_id(PLATFORM, thread_id)

    # Prefer the local copy where it reaches further back than the live scrape,
    # keeping the live posts for the tail because they are the current state.
    scraped = load_scraped_thread(thread_id)
    if len(scraped) > len(earlier_posts):
        live_numbers = {_as_dict(p).get("post_number") for p in earlier_posts}
        older = [p for p in scraped if p.get("post_number") not in live_numbers]
        earlier_posts = older + list(earlier_posts)
        log_debug(f"Forum: thread {thread_id} — {len(scraped)} posts on disk, "
                  f"using the last {MAX_THREAD_HISTORY_TURNS} of {len(earlier_posts)}.")

    turns = []
    for post in earlier_posts[-MAX_THREAD_HISTORY_TURNS:]:
        d = _as_dict(post)
        text = own_words(d) or _readable(d.get("content") or "")
        if not text:
            continue
        author = (d.get("author") or "").strip()
        mine = author.lower() == (username or "").lower()
        turns.append({
            "role": "assistant" if mine else "user",
            "content": text if mine else f"{author}: {text}",
            # A float, like every other writer of channel_memory. This was a
            # string, so anything sorting the merged history numerically threw
            # or silently fell back to insertion order.
            "timestamp": time.time(),
            # These are forum posts, not Discord messages. channel_memory is
            # shared, and `conversation_channel_id` hands back a plain int
            # (crc32 % 10**10), so nothing downstream can tell a thread from a
            # channel by its key. Consumers that mean "my Discord server" —
            # the inner monologue above all — filter on this.
            "external": PLATFORM,
        })

    try:
        # Bounded, like every other channel. A bare list here grew without a
        # maxlen and became the largest thing in channel_memory.
        from collections import deque
        bot_state.channel_memory[channel_id] = deque(
            turns, maxlen=max(len(turns), int(config.get("max_memory_messages", 50))))
    except Exception:
        return 0
    log_info(f"Forum: seeded {len(turns)} thread posts as conversation history "
             f"for thread {thread_id}.")
    return len(turns)


async def draft_forum_reply(ctx, *, thread_id: int, title: str, posts: list,
                            reply_to: Optional[dict] = None,
                            quote: Optional[bool] = None) -> Optional[dict]:
    """Draft a post for `thread_id`, or None if she should stay quiet.

    Returns {'text', 'quote'} where 'text' is the BBCode-ready post body.
    """
    if not posts:
        log_warning(f"Forum: no posts to respond to in thread {thread_id}.")
        return None

    username = os.getenv("VBULLETIN_USERNAME", "")

    # `format_thread_context` used to be assembled here and then never sent
    # anywhere — a leftover from when this function built its own prompt. The
    # thread reaches the model as conversation history via `seed_thread_history`
    # below, which is the shape the pipeline actually reads. The function is now
    # exercised only by tests; it is kept because a thread flattened into one
    # block is the readable form when debugging what she was given.

    # The target is explicit in every case. Previously, when the coin flip came
    # up "no quote", reply_to was None and the model was left to infer who it
    # was answering from the tail of the thread block.
    quote_post = reply_to if reply_to is not None else pick_quote_target(posts, username)
    if quote is False:
        quote_post = None

    # Shaped exactly like a Discord message, because it goes through the Discord
    # pipeline.
    #
    # This had it backwards: the *thread* was sent as [USER_MESSAGE] and the
    # person's actual post as [REPLYING_TO] background. So the model was
    # answering the thread, with the message it was supposed to answer demoted
    # to context — which is why a reply to "test test hello hello" came back
    # about the Well-Formed Outcome Process. In Discord the message is the
    # message; here it now is too.
    #
    #   [ORIGINAL_POST] the rest of the thread, as background
    #   [USER_MESSAGE]  what this person actually said
    target = quote_post if quote_post else _as_dict(posts[-1])
    speaker = target.get('author', 'Someone')
    speaker_id = target.get('user_id') or 0
    their_words = own_words(target) or (target.get('content') or '').strip()

    # `[REPLYING_TO]` must be non-empty whatever happens: `root_context` is
    # injected *inside* `if ctx.parent_context:`, so an empty antecedent silently
    # discards the thread background with it.
    #
    # What they were replying to — and on a forum that is what they *quoted*,
    # nothing else.
    #
    # This used to walk backwards from the target and take the first earlier post
    # in the thread. In a two-person exchange that is right; in the 177-post
    # threads she actually posts in it hands her a different person arguing a
    # different point and labels it as the thing she is answering. The operator
    # saw the result as posts that "inject unrelated context from previous posts
    # by different people".
    #
    # When they quoted nobody, the honest answer is that there is no antecedent,
    # and the fallback below uses their own words — the same shape as a Discord
    # message sent without a reply attached.
    quoted_author, previous = quoted_context(target)
    if previous:
        log_debug(f"Forum: {speaker} was answering {quoted_author or 'an earlier post'}; "
                  f"using that as the antecedent.")
    else:
        log_debug(f"Forum: {speaker} quoted nobody; answering their post on its own terms.")

    content = (f"[REPLYING_TO]\n{previous or their_words}\n"
               f"[USER_MESSAGE]\n{their_words}")

    # The thread is the conversation, so it goes in as conversation history —
    # the same channel memory Discord reads, in the same shape.
    #
    # Without this the forum had no history at all. Discord replies draw on the
    # accumulated turns of a channel; a forum thread maps to a channel id that
    # nothing ever writes to, so `optimize_context` received an empty list and
    # she answered every post cold. That is most of what "boilerplate one
    # sentence" was: no conversation to be in the middle of.
    seed_thread_history(ctx, thread_id, posts[:-1] if len(posts) > 1 else [], username)

    from utils.infrastructure.system.external_mention import process_external_mention

    # No retries, no nudges, no extra instructions. The pipeline is asked once,
    # exactly as Discord asks it, and whatever comes back is the draft.
    #
    # Two previous attempts to "help" here both made it worse. A length floor of
    # 24 characters dropped "hello." — a fair reply to "test test hello hello" —
    # and logged that the filters had emptied it, which they had not. Replacing
    # that with a retry that said "reply to what the THREAD is about instead"
    # produced a post about the Well-Formed Outcome Process, a topic lifted at
    # random from the thread context and unrelated to the message being
    # answered. An irrelevant post is worse than a short one.
    reply = (await process_external_mention(
        ctx=ctx, content=content, author_name=speaker, author_id=speaker_id,
        platform=PLATFORM,
        # Per-thread memory. Without this every thread on the site would share
        # one conversation history.
        conversation_key=thread_id,
        # Draft only. The forum poster is being quoted, not conversed with.
        no_persist=True,
    ) or "").strip()

    if not reply:
        log_warning("Forum: the pipeline returned nothing, skipping.")
        return None

    # The one thing still worth refusing: the canned apology the pipeline
    # returns when generation genuinely failed. That is not a post.
    if is_generation_failure(reply):
        log_warning(f"Forum: generation failed, not drafting a post: {reply[:60]!r}")
        return None

    # Would this read as the same post again? Her forum posts sit permanently
    # side by side on a profile page, where a repeated opening is far more
    # visible than it is in a scrolling chat.
    ledger = PostLedger()
    # Published posts *and* drafts the operator turned down. A rejection is the
    # strongest signal available about what she should not send, and it was being
    # thrown away: only `posts` was consulted, so the guard could not tell that
    # the paragraph in front of it had already been refused once.
    recent_bodies = [p.get("body", "") for p in ledger.posts_since(14 * 24)]
    recent_bodies += ledger.rejected_bodies()
    repetitive, why = looks_repetitive(
        reply, recent_bodies,
        threshold=float(config.get('forum.max_self_similarity', 0.5)))
    if repetitive:
        log_info(f"Forum: holding a draft that repeats herself — {why}.")
        return None

    return {'text': reply, 'quote': quote_post}

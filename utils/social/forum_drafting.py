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
from typing import Any, Optional

from utils.infrastructure.logging.kaia_logger import log_info, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.social.forum_participation import PostLedger, looks_repetitive

# vBulletin's own platform tag. The processor keys its forum-specific prompt
# assembly off this exact string; `forum_tasks` used to pass "forum", which
# silently took the ordinary Discord path and lost the thread context entirely.
PLATFORM = "vbulletin"


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


def own_words(content: str, limit: int = 700) -> str:
    """A poster's own text, without whatever they were quoting."""
    lines, out = (content or "").split("\n"), []
    for line in lines:
        if _NESTED_QUOTE.match(line):
            break
        out.append(line)
    text = "\n".join(out).strip()
    if not text:                       # the post was only a quote plus a reaction
        text = (content or "").strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return text


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
    thread_block = format_thread_context(title, posts)

    # The target is explicit in every case. Previously, when the coin flip came
    # up "no quote", reply_to was None and the model was left to infer who it
    # was answering from the tail of the thread block.
    quote_post = reply_to if reply_to is not None else pick_quote_target(posts, username)
    if quote is False:
        quote_post = None

    # The processor unwraps these markers; [REPLYING_TO] becomes
    # ctx.parent_context, which the vbulletin branch turns into the user turn.
    if quote_post:
        author = quote_post.get('author', 'Unknown')
        content = (f"[REPLYING_TO]\n{own_words(quote_post.get('content', ''))}\n"
                   f"[USER_MESSAGE]\n{thread_block}")
        speaker, speaker_id = author, quote_post.get('user_id') or 0
    else:
        last = _as_dict(posts[-1])
        content = thread_block
        speaker, speaker_id = last.get('author', 'Someone'), last.get('user_id') or 0

    from utils.infrastructure.system.external_mention import process_external_mention
    reply = await process_external_mention(
        ctx=ctx, content=content, author_name=speaker, author_id=speaker_id,
        platform=PLATFORM,
        # Per-thread memory. Without this every thread on the site would share
        # one conversation history.
        conversation_key=thread_id,
    )

    reply = (reply or "").strip()
    if len(reply) < 24:
        log_warning("Forum: draft was empty or emptied by the filters, skipping.")
        return None

    # Would this read as the same post again? Her forum posts sit permanently
    # side by side on a profile page, where a repeated opening is far more
    # visible than it is in a scrolling chat.
    ledger = PostLedger()
    recent_bodies = [p.get("body", "") for p in ledger.posts_since(14 * 24)]
    repetitive, why = looks_repetitive(
        reply, recent_bodies,
        threshold=float(config.get('forum.max_self_similarity', 0.5)))
    if repetitive:
        log_info(f"Forum: holding a draft that repeats herself — {why}.")
        return None

    return {'text': reply, 'quote': quote_post}

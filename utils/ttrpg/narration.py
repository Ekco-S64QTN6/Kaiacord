"""
Narration helpers for the TTRPG event system.

Every narrated event — raids, breaches, combat summaries, social scenes — asks
the model for prose and posts it to Discord. Ten such call sites set a fixed
`num_predict` and **none** checked whether the model had actually finished a
sentence, so hitting the cap published output cut mid-word:

    "...jimjam fought an iron golem, each blow reverberating against the
     construct's unyielding armor. the defenders of o"

Two problems, handled separately here:

  * a budget that does not scale with how much the narrator was asked to cover
    (`raid_token_budget`);
  * publishing a truncated generation at all (`finish_cleanly`).
"""
from __future__ import annotations

import re

# Discord's hard limit on an embed description. Narration is wrapped in
# asterisks for italics, so the usable budget is two characters less.
EMBED_DESCRIPTION_LIMIT = 4096

# Sentence-final punctuation, including the quote/bracket forms that can follow.
_SENTENCE_END = re.compile(r'[.!?…]["\')\]]?\s*$')
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?…])[\s]+')

#: Never trim away more than this fraction chasing a sentence boundary — a
#: paragraph with no full stop should be kept, not gutted.
MAX_TRIM_FRACTION = 0.35


def looks_truncated(text: str) -> bool:
    """True if the text does not end on sentence-final punctuation."""
    stripped = (text or "").rstrip()
    return bool(stripped) and not _SENTENCE_END.search(stripped)


def finish_cleanly(text: str) -> str:
    """Trim a possibly mid-word generation back to its last complete sentence.

    Returns the text unchanged when it already ends cleanly. When trimming
    would cost more than MAX_TRIM_FRACTION of the text — a long passage with no
    terminal punctuation — the text is kept and closed with an ellipsis
    instead, because losing a third of a battle report is worse than an
    unfinished clause.
    """
    stripped = (text or "").strip()
    if not stripped or not looks_truncated(stripped):
        return stripped

    parts = _SENTENCE_SPLIT.split(stripped)
    if len(parts) > 1:
        kept = " ".join(parts[:-1]).rstrip()
        if kept and len(kept) >= len(stripped) * (1.0 - MAX_TRIM_FRACTION):
            return kept

    # Nothing safe to trim to: close the dangling clause rather than ship a
    # half-word. Drop a trailing partial word first.
    trimmed = re.sub(r'\s+\S*$', '', stripped) if ' ' in stripped else stripped
    return (trimmed or stripped).rstrip(' ,;:-—') + '…'


def fit_embed_description(text: str, wrapper_chars: int = 2) -> str:
    """Clamp narration to Discord's embed limit, on a sentence boundary.

    `wrapper_chars` accounts for markup the caller adds around the text (the
    raid summary wraps it in asterisks). Sending an over-long description
    raises rather than truncating, which would lose the whole post.
    """
    limit = EMBED_DESCRIPTION_LIMIT - wrapper_chars
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return finish_cleanly(text[:limit])


def raid_token_budget(participant_count: int,
                      base: int = 260,
                      per_participant: int = 55,
                      ceiling: int = 900) -> int:
    """Token budget for a narration covering `participant_count` fights.

    The raid summary asks for a beat per defender. A fixed 300 tokens covered
    roughly three of them; a six-defender raid ran out mid-sentence. Scaling
    with the cast is what stops the cap being hit in the first place —
    finish_cleanly only makes the failure tidy.
    """
    return min(ceiling, base + per_participant * max(0, participant_count))

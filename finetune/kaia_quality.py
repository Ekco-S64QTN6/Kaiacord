"""What makes a Kaia turn good enough to train on.

One definition, shared by the builder (`01_convert_logs.py`), the pre-flight
gate (`01f_clean_targets.py`), the length audit (`01d_scan_length_outliers.py`)
and the evaluation (`05c_evaluate_persona.py`), so the four cannot drift apart.

A target is the text Kaia should have said. It goes through the live runtime
filters first, so the model learns what the pipeline would have delivered, and
then through a stricter gate: the runtime tolerates some registers because a
false positive there costs a regeneration on someone's turn, while a bad
training example is learned and amplified. Every rule in the gate is a register
`knowledge_base/kaia_persona.md` bans by name, matched by vocabulary rather
than by shape, so an unrecognised sentence is kept.

Command-line entry points call `quiet()` first: a build makes tens of
thousands of filter calls, and each strip would otherwise log a warning.
"""
from __future__ import annotations

import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.core.response_filter import BotSpeakFilter, EmergencyContaminationFilter  # noqa: E402


def quiet() -> None:
    """Silence the filters' per-strip logging for a batch run. Process-wide,
    so only a script's main() calls it, never an import."""
    import utils.core.response_filter as rf
    logging.disable(logging.CRITICAL)
    for name in ("log_warning", "log_info", "log_debug"):
        if hasattr(rf, name):
            setattr(rf, name, lambda *a, **k: None)

#: A target shorter than this after cleaning is no longer a usable example.
MIN_TARGET_CHARS = 24
#: Longer than this is a pasted article or an essay, not a reply.
MAX_TARGET_CHARS = 1000
#: MAX_SEQ_LENGTH in 03_train.py. Longer examples are truncated by the trainer,
#: which cuts the target mid-sentence and teaches the model to stop there.
TRAIN_MAX_TOKENS = 1024
#: Used only when the real tokenizer is not available; errs toward too many tokens.
CHARS_PER_TOKEN = 3.2

# An ellipsis in prose: the character, three dots, or two dots between letters
# ("system..it"). Two dots anywhere else are a path or a range ("../config",
# "1..10") and are left alone.
_ELLIPSIS = r"(?:…|\.{3,}|(?<=[a-z])\.\.(?=[ \ta-z]))"


def normalize_ellipses(text: str) -> str:
    """Take the trailing-off cadence out and keep the sentence.

    `EmergencyContaminationFilter.defuse_ellipsis_affect` handles the copula
    form and turns every other ellipsis into a full stop, which leaves
    "it's a. peculiar development" when the ellipsis followed an article. Here
    an ellipsis that runs on into more of the sentence becomes a space, and one
    that ends a thought becomes a full stop.
    """
    text = re.sub(_ELLIPSIS + r"(?=[ \t]*[a-z0-9\"'(])", " ", text)
    text = re.sub(r"(\w)" + _ELLIPSIS, r"\1.", text)
    text = re.sub(_ELLIPSIS, "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


# ── Damage ───────────────────────────────────────────────────────────
#
# Logged turns are what was delivered, and some were delivered with holes cut
# by guards since fixed: an italic title deleted ("a piece like stravinsky's ;"),
# an article stranded ("the image depicts a, commonly known as"), words fused
# ("the.gravy"). A sentence with a hole in it teaches the hole.
_RUBBLE = re.compile(
    r"[^\S\n]{2,}\S"                              # a gap where something was cut
    r"|\S[^\S\n]+[,;:](?=\s|$)"                   # "is ;", "stravinsky's ;"
    r"|(?m:^[ \t]*[,;:.])"                        # a line opening on punctuation
    r"|\b(?:the|a|an|my|your)[ \t]*[,;:!?](?=\s|$)"   # a stranded article
    r"|\b(?:the|a|an|my|your)\.(?=\s|$)"
    r"|\b(?:the|an)\.[a-z]{2,}"                   # "the.gravy"
    r"|,[ \t]*[.;]"
    r"|\b(?:the|a|an)[ \t]+(?:is|are|was|were|has|have|and|of|to)\b",   # "the is unsettling"
    re.IGNORECASE,
)


def broken(text: str) -> bool:
    """A hole cut by a guard, or a run of forty-five words with no sentence
    break, which is what a guard that strips full stops leaves behind."""
    if _RUBBLE.search(text or ""):
        return True
    if len((text or "").split()) >= 12 and not re.search(r"[.!?]", text or ""):
        return True
    return any(len(run.split()) > 45 for run in re.split(r"[.!?;:\n]", text or ""))


# The registers live with the runtime, which uses them for the agent boards;
# this module re-exports them so the dataset tools keep one definition.
from utils.core.persona_register import (  # noqa: E402,F401
    _ANALYTIC, analytic, _UNCONTRACTED, _CONTRACTED, formal, PERSONA_REJECT, NOT_A_NAME, opens_on_a_name, persona_reject, _STOP, _content_words, echoes)


# Targets use straight quotes, as people type them; every rule here is written
# with them, and a curly apostrophe let "here\u2019s a summary" past the gate.
_STRAIGHT = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def clean_target(text: str) -> tuple[str | None, str]:
    """(cleaned text, "kept") or (None, why it cannot be a target)."""
    raw = (text or "").strip()
    if not raw:
        return None, "empty"
    filtered = EmergencyContaminationFilter.filter_response(raw)
    if filtered is None:
        return None, "runtime_would_regenerate"
    # Until nothing changes: one pass can expose what the next removes (a name
    # left alone on its first line once the clause after it is gone).
    cleaned = filtered
    for _ in range(4):
        again = normalize_ellipses((BotSpeakFilter.harden(cleaned) or "").strip()).strip().translate(_STRAIGHT)
        if again == cleaned:
            break
        cleaned = again
    if len(cleaned) < MIN_TARGET_CHARS:
        return None, "too_short"
    if len(cleaned) > MAX_TARGET_CHARS:
        return None, "too_long"
    if broken(cleaned):
        return None, "broken_grammar"
    bad = persona_reject(cleaned)
    if bad:
        return None, bad
    if formal(cleaned):
        return None, "formal_register"
    if analytic(cleaned):
        return None, "analytic_register"
    return cleaned, "kept"


# ── Near-duplicates ──────────────────────────────────────────────────
#
# Exact de-duplication misses the repeats that matter: the status reply said
# forty times with the details shuffled, or a nightly journal entry that opens
# "i'm finding myself less inclined to dissect the why" every other night. Each
# repeat pulls the model further toward that one answer.
def _shingles(text: str, n: int = 3) -> frozenset:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    if len(words) < n:
        return frozenset([" ".join(words)])
    return frozenset(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))


class NearDuplicates:
    """Remembers kept texts; `seen(text)` is True when one is too similar."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._sets: list[frozenset] = []
        self._index: dict[str, list[int]] = defaultdict(list)

    def seen(self, text: str) -> bool:
        s = _shingles(text)
        overlap: dict[int, int] = defaultdict(int)
        for g in s:
            for i in self._index.get(g, ()):
                overlap[i] += 1
        for i, shared in overlap.items():
            if shared / (len(s) + len(self._sets[i]) - shared) >= self.threshold:
                return True
        return False

    def add(self, text: str) -> None:
        s = _shingles(text)
        idx = len(self._sets)
        self._sets.append(s)
        for g in s:
            self._index[g].append(idx)


# ── Length in real tokens ────────────────────────────────────────────
_TOKENIZER = None


def tokenizer():
    """Gemma 3's tokenizer from the local Hugging Face cache, or None."""
    global _TOKENIZER
    if _TOKENIZER is None:
        try:
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from transformers import AutoTokenizer
            _TOKENIZER = AutoTokenizer.from_pretrained(
                "unsloth/gemma-3-12b-it-bnb-4bit", local_files_only=True)
        except Exception:
            _TOKENIZER = False
    return _TOKENIZER or None


def example_tokens(messages: list[dict]) -> int:
    """Tokens in the rendered example, as the trainer will see it."""
    tok = tokenizer()
    if tok is None:
        return int(sum(len(m.get("content") or "") for m in messages) / CHARS_PER_TOKEN) + 8 * len(messages)
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return len(tok(text.removeprefix(tok.bos_token or ""))["input_ids"])


# ── Replies to something the log does not hold ──────────────────────
#
# The live prompt carried the linked page, the embed and the picture; the log
# keeps only what the person typed. A reply grounded in them, trained against
# the typed words alone, teaches her to describe what she cannot see:
# "the document outlines a collaborative project…" to a bare link, a pangolin
# lecture to a message about mushroom spores.
_URL = re.compile(r"https?://", re.I)
_DESCRIBES_A_PICTURE = re.compile(
    r"\b(the (image|photo|picture|drawing|screenshot|video|clip|document|article|page|post|link)|"
    r"(this|that) (image|photo|picture|drawing|screenshot)|image depicts|pictured|in the foreground|"
    r"in the background|the object in)\b", re.I)


# Pointing at a picture without naming it: "what kind of fish are these in this cage?"
_POINTS_AT_A_PICTURE = re.compile(
    r"\b(this|these|those) (fish|cats?|birds?|bugs?|insects?|plants?|pics?|pictures?|images?|photos?|"
    r"drawings?|paintings?|screenshots?)\b|\bin (this|the) (cage|pic|picture|photo|image|shot)\b|"
    r"\bwhat (is|are) (this|these)\b|\bhighlighted\b|\blook at (this|these|that)\b", re.I)


def needs_unseen_context(raw_user: str, typed: str, target: str) -> bool:
    return (typed.strip() != (raw_user or "").strip() or bool(_URL.search(raw_user or ""))
            or bool(_POINTS_AT_A_PICTURE.search(typed or ""))
            or bool(_DESCRIBES_A_PICTURE.search(target or "")))


# ── Human review ─────────────────────────────────────────────────────
#
# The gate removes what can be named; judging the rest of a reply takes a
# person. `01g_review.py` records a decision per target here, keyed by the
# cleaned text, and the builder honours it on every rebuild.
REVIEW_FILE = Path(__file__).resolve().parent / "dataset" / "review.jsonl"


def review_key(target: str) -> str:
    import hashlib
    return hashlib.sha1(target.strip().encode("utf-8")).hexdigest()[:16]


def load_reviews() -> dict[str, dict]:
    """The latest decision for each reviewed target."""
    import json
    out: dict[str, dict] = {}
    if REVIEW_FILE.exists():
        for line in REVIEW_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["key"]] = rec
    return out

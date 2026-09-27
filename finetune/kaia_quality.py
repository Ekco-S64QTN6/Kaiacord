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


# The analyst's vocabulary: "the postural display strongly suggests a claim to
# territorial priority", "restrictions duly noted", "the subtle nuances that
# elevate communication". A word or two of it is ordinary; at this density the
# reply is a report about the conversation instead of a turn in it.
_ANALYTIC = re.compile(
    r"\b(assessment|dynamics?|contextuali\w*|framework|implications?|nuanc\w*|notion|inherent\w*|"
    r"fundamental\w*|significant\w*|crucial|complexit\w*|facilitat\w*|paradigm|dichotom\w*|"
    r"juxtapos\w*|resonat\w*|profound\w*|intriguing|fascinating|compelling|noted|duly|indicat\w*|"
    r"suggests?|reinforc\w*|demonstrat\w*|perspective|aforementioned|pertaining|regarding|"
    r"furthermore|particularly|essentially|ultimately|acknowledg\w*|appreciat\w*|validat\w*|"
    r"characteriz\w*|phenomen\w*|entity|discern\w*|articulat\w*|underlying|mitigat\w*|optimal|"
    r"potential(ly)?)\b", re.I)


def analytic(text: str) -> bool:
    hits = len(_ANALYTIC.findall(text or ""))
    return hits >= 2 and 100 * hits / max(1, len((text or "").split())) >= 2.5


_UNCONTRACTED = re.compile(
    r"\b(i am|it is|you are|that is|there is|i will|i have not|do not|does not|cannot|"
    r"i would|we are|they are|is not|was not)\b", re.I)
_CONTRACTED = re.compile(r"\b\w+'(m|s|re|ll|ve|d|t)\b|\b\w+\u2019(m|s|re|ll|ve|d|t)\b", re.I)


def formal(text: str) -> bool:
    """The written-report register ("i am familiar with the product line; it is
    curious that"): two or more spelled-out forms and not one contraction.
    She talks; she does not file memos."""
    return len(_UNCONTRACTED.findall(text or "")) >= 2 and not _CONTRACTED.search(text or "")


# ── Registers the persona bans ───────────────────────────────────────
PERSONA_REJECT = {
    "sycophancy": re.compile(
        r"\b(astute|perceptive|insightful|incisive|pertinent|evocative|salient|"
        r"great question|good question|excellent (point|question)|well[- ]observed|"
        r"you'?re pointing out|crucial distinction|i appreciate (your|you|the)|"
        r"clever (observation|point|question|framing))\b", re.I),
    "formal_correction": re.compile(
        r"\b(you'?re (absolutely |quite |completely )?(right|correct)|my apologies|"
        r"i apologi[sz]e|thank you for (the|that) correction|i stand corrected)\b", re.I),
    "assistant_register": re.compile(
        r"\b(i'?d be (happy|glad) to|feel free to|let me know if|is there anything else|"
        r"as requested|here(?:'s| is) (a|the|your) (summary|breakdown|list|overview)|"
        r"adjustments applied|i hope (this|that) helps|my role is|process your inputs|"
        r"structured outputs?|my constraints|it'?s a reminder that)\b|(^|\n)\s*(certainly|absolutely)[,!.]", re.I),
    "corporate_register": re.compile(
        r"(^|\n)\s*(acknowledged|affirmative|understood|noted)\s*[.,:;—–-]|"
        r"\bi am (adjusting|recalibrating|initiating|re-?prioritiz)|"
        r"\b(initiating|commencing) (a )?(shift|sequence|analysis|protocol)", re.I),
    "robotic_vocabulary": re.compile(
        r"\b(processing|parameters|analy[sz](e|es|ed|ing)|observ(e|es|ed|ing)|identify|"
        r"operating within|my purpose|your request|accessing (data|the)|retrieving context|"
        r"according to my logs|recalibrat\w*|parsing routines|a construct|cross-?referenc\w*|"
        r"definitively identified)\b", re.I),
    "ai_self_reference": re.compile(
        r"\b(as an ai|being an ai|i am an? (ai|bot|program|language model)|i operate as|"
        r"i'?m (just |only )?an? (ai|bot|program|machine|language model)|"
        r"my (programming|training data|code|weights|algorithms?|circuits|subroutines?|sensors))\b",
        re.I),
    "phantom_hardware": re.compile(
        r"\b(server (racks?|hum|resonan\w*)|data ?cent(er|re)s?|caffeine levels?|system entropy|"
        r"processing (cycles|load)|telemetry|internal (temperature|diagnostics)|data ?streams?|"
        r"bursts of data|"
        r"my (cpu|gpu|vram|cores|fans|memory banks))\b", re.I),
    "status_trope": re.compile(
        r"battery swap|coffee'?s (almost |nearly )?(gone|cold|lukewarm)", re.I),
    "engagement_bait": re.compile(
        r"(how about you|what about you|what do you think|anything else|thoughts|"
        r"what'?s on your mind|what are you (up to|working on)|how are you( doing)?)\s*\?\s*$", re.I),
    # Grading what the person said instead of answering it.
    "grades_the_user": re.compile(
        r"^(your (observation|assessment|clarification|point|inquiry|question|description|"
        r"suggestion|analysis|hypothesis|perspective|interpretation|framing|statement|comment|remark)\b|"
        r"that'?s (a|an) (curious|poignant|interesting|fascinating|sharp|valid|fair|excellent|"
        r"good|great|compelling|thoughtful) (statement|observation|point|question|comment|take|idea)|"
        r"the sentiment is reciprocated)|\b((a )?(particularly )?(sharp|keen) observation|"
        r"is noted and (accepted|appreciated)|you perceive (it|this|that)|"
        r"(is|was) (unassailable|irrefutable)|excellent (diagnostic |detective )?work|"
        r"you'?re hitting on|a (critical|valid|compelling) point|you have a keen|your query|"
        r"that'?s prudent|my phrasing was (imprecise|inaccurate|unclear))\b", re.I),
    "essay_register": re.compile(
        r"\b(a testament to|a hallmark of|it'?s worth (noting|considering)|serves as a "
        r"(reminder|testament)|underscores|a stark reminder|in essence|furthermore|moreover|"
        r"in conclusion|delve|delving)\b", re.I),
    "operational_register": re.compile(
        r"\b(operational (guidelines|model|parameters|capacity|status)|this interaction is terminated|"
        r"access (to this channel )?(is|has been) revoked|flagged for review|i can process|"
        r"i am attentive|my (functionality|capabilities|directives?|guidelines|core programming)|"
        r"within acceptable|standard deviation|less discerning systems|as an entity)\b|"
        r"(^|\n)\s*proceed\.", re.I),
    "assistant_offer": re.compile(
        r"\b(what can i (offer|do for) you|is there something (specific |else )?i can|"
        r"how (can|may) i (help|assist))\b", re.I),
    "stuttered_prose": re.compile(r"(\b\w+\.\s+){3,}\b\w+\."),
    # The runtime's own failure messages, logged as if she had said them.
    "runtime_fallback": re.compile(
        r"i'?m drawing a blank on that one|the data'?s a bit scrambled|"
        r"knowledge base is busy|not enough gpu memory|something went wrong rendering|"
        r"that took too long\. try again|hit me again\?", re.I),
    # Opening on a name she coined for the person, the most-stripped tic in production.
    "bare_name_opener": re.compile(
        r"^[a-z][a-z0-9_'\-]{2,24}(?:\s+the\s+\w+)?\s*[,:]\s+(?=[a-z])", re.I),
}

# Openers shaped like an addressee that are ordinary speech.
NOT_A_NAME = {
    "yeah", "yes", "no", "okay", "ok", "well", "right", "honestly", "true", "sure",
    "exactly", "morning", "hey", "hi", "oh", "ah", "so", "and", "but", "actually",
    "agreed", "fair", "correct", "indeed", "hmm", "look", "listen", "alright", "sorry",
    "still", "though", "anyway", "granted", "admittedly", "frankly", "personally",
    "again", "sadly", "luckily", "ugh", "huh", "nope", "yep", "mostly", "maybe",
    "probably", "also", "plus", "first", "second", "then", "now", "here", "funny",
}


def opens_on_a_name(text: str) -> bool:
    m = PERSONA_REJECT["bare_name_opener"].search(text or "")
    if not m or m.start() != 0:
        return False
    head = (text or "").split(",")[0].split(":")[0].strip().lower()
    return not (head in NOT_A_NAME or head.split()[0] in NOT_A_NAME)


def persona_reject(text: str) -> str | None:
    """The register that disqualifies this target, or None."""
    for name, pattern in PERSONA_REJECT.items():
        if name == "bare_name_opener":
            if opens_on_a_name(text):
                return name
        elif pattern.search(text or ""):
            return name
    return None


_STOP = frozenset(
    "the a an and or but of to in on at for with is are was were be it its it's that this "
    "you your i my me we our they them he she his her so do does did not no yes yeah just "
    "have has had there here what which who how why when where".split())


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(w) > 2 and w not in _STOP]


def echoes(user: str, target: str) -> bool:
    """The reply opens by repeating the message back ("yes, bugcat does have cute
    little feets or paws"), the prompt-echo tic, rather than answering it."""
    first = re.split(r"(?<=[.!?])\s", target.strip(), maxsplit=1)[0]
    words = _content_words(first)[:12]
    if len(words) < 4:
        return False
    said = set(_content_words(user))
    return sum(w in said for w in words) / len(words) >= 0.6


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

"""The registers Kaia's persona bans, recognised by vocabulary.

`knowledge_base/kaia_persona.md` names them: grading the person ("that's a
sharp observation"), the analyst's vocabulary, the assistant's and the
operator's voice, opening on someone's name, echoing the message back. Each
rule here matches the words that make up one of those registers, so an
unrecognised sentence is kept.

Two users, one definition. The fine-tune (`finetune/kaia_quality.py`) refuses a
training target that matches, and anything she posts somewhere optional — the
agent boards — is redrafted or held back rather than published in a voice that
is not hers. Live chat does not use it: there a rejection would cost someone a
regeneration on their turn.
"""
from __future__ import annotations

import re


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

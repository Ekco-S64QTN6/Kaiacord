# ---------------------------------------------------------------------------
# Phase 3b additional BANNED_STRINGS — paste these into the BANNED_STRINGS
# list in finetune/01_convert_logs.py
#
# Source: patterns found in Ekco interaction log analysis (2026-03-04)
# These are essay-mode / generic-AI phrases that never appear in real Kaia voice.
# ---------------------------------------------------------------------------

ADDITIONAL_BANNED_STRINGS = [
    # Essay-mode connectors (from GLM-5, deanonymization, 6G responses)
    "this underscores",
    "it's a stark reminder",
    "it necessitates",
    "it renders",
    "a commendable",
    "it is imperative",
    "it is worth noting",
    "far-reaching consequences",
    "far-reaching implications",
    "has the potential to",
    "it's a sobering reminder",
    "the underlying message",
    "it's a disturbing demonstration",
    "it's a classic case of",
    "it's a reminder that",
    "it's fascinating to see",

    # Robotic action narration (without asterisks — not caught by "*" filter)
    "pause - approximately",
    "pause – approximately",
    "accessing and reviewing",
    "accessing and reading",
    "i'm noting that feedback",
    "i'm observing that",
    "i'm reviewing the",
    "i'm marking this",
    "i'm flagging this",

    # Robotic acknowledgment openers
    "the document details",
    "the article details",
    "the filing details",
    "per the coalition",
    "per the report",
    "the findings have the potential",

    # Generic AI wrap-up phrases
    "a rather amusing and entirely avoidable",
    "a correction to the detection algorithm is clearly warranted",
    "it's ironic, isn't it?",    # rhetorical question Kaia wouldn't ask
]

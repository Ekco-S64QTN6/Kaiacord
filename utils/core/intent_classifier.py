"""
Intent Classification
=====================

Extracted from kaia_intelligence.py (Phase 28 / CQ-01).

Contains:
- IntentParser: Advanced intent understanding engine with fast-path triggers and LLM analysis
- QueryClassifier: Legacy alias for IntentParser
"""

import re
import json
from typing import Optional

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_debug
)
from utils.core.context_optimizer import Intent

# Pre-compiled regex patterns used by IntentParser
RE_MD_JSON_BLOCK_START = re.compile(r'```json\s*')
RE_MD_BLOCK_BACKTICKS = re.compile(r'```')
RE_THINK_BLOCK = re.compile(r'<think>[\s\S]*?</think>')


class IntentParser:
    """
    Advanced Intent Understanding Engine. 
    Replaces simple classification with cognitive intent parsing.
    """
    

    def __init__(self, ollama_client=None, model=None, logger=None,
                 host="http://localhost:11434", timeout=120.0):
        """Regex intent matching. No model is loaded and none is called.

        The arguments are kept so existing call sites and tests keep working;
        they are ignored. This class used to hold an Ollama client, a
        `classification_model` (gemma2:2b), CPU option tuning and a pre-warm
        routine for a second LLM pass — `parse_intent` / `_analyze_with_llm` —
        that ran on every ambiguous message and whose verdict nothing ever
        read. `ctx.intent` was only ever assigned from `fast_parse`, so the
        model was pulled, warmed, held ~1.6 GB of host RAM and answered 135
        times in one production log, into the void.
        """
        self.logger = logger or log_info


        # LAYER 1: Fast Pattern Triggers (Precompiled for performance)
        self.fast_triggers = {}
        raw_triggers = {
            "SOCIAL_GREETING": [
                r"^\s*(<@!?\d+>\s*)?(kaia|hey kaia|hi kaia|hello kaia)[!?.,]*\s*$",
                r"^\s*(<@!?\d+>\s*)?(hi|hello|hey|greetings|sup|yo|hi there|hello there)[!?.,]*\s*$",
                r"^\s*(<@!?\d+>\s*)?(hi|hello|hey|greetings|sup|yo)\s+kaia[!?.,]*\s*$",
                r"^\s*(<@!?\d+>\s*)?kaia[!?.,]*$"
            ],
            "COMMAND_EXECUTION": [
                # The whole message is the command. As a prefix it took "kaia
                # clear skies today..." and "stats on that sword" down the
                # no-retrieval shortcut; clear and reset do nothing here.
                r"^\s*(kaia\s+)?(status|stats|ping|uptime|quip)(\s+kaia)?[!?.,]*\s*$",
                r"^\s*[!/](quip|news|dreams|cache)\b"
            ],
            "DREAM_RECALL": [
                # Her dreams, not the word: "my dream car", "a nightmare of a
                # day" and "Do Androids Dream..." routed to the dream index
                # alone, which kept the book itself out of retrieval.
                r"\b(you|your)\s+(\w+\s+)?(dream(s|t|ed|ing)?|nightmares?)\b",
                r"\bany\s+(recent\s+|good\s+|weird\s+)?(dreams|nightmares)\b",
                r"\b(dream(s|t|ed)?|nightmares?)\s+(last night|lately|recently)\b",
                r"^\s*(kaia\s+)?what did you dream",
                r"^\s*(kaia\s+)?tell me about your dream",
                r"^\s*(kaia\s+)?any recent dreams"
            ],
            "PRECISE_RECALL": [
                r"^\s*(kaia\s+)?who (is|are|was|were|am) ",
                r"^\s*(kaia\s+)?what (is|are|was|were) ",
                r"\b(dossier on|tell me about|biography of|background on)\b",
                r"\b(elara|thorne|jules|elias)\b"
            ],
            "DIAGNOSTIC_DEEP_DIVE": [
                # About her or a program, not the words in passing: "the solar
                # system", "the status quo", "fix your hair", "hang out" and
                # every x.com link (…/status/…) were all diagnostics, which
                # searches chat logs only and runs the turn at the grounded
                # temperature.
                r"\b(errors?|bugs?|crash(ed|es|ing)?|exceptions?|traceback|dogshit)\b",
                r"\b(your|kaia'?s)\s+(logs?|status|system|code|memory|filters?|pipeline)\b",
                r"\b(restart|reboot|debug(ging)?)\b",
                r"\b(why is it slow|latency|lockup)\b"
            ],
            "RECAP_QUERY": [
                r"recap\b.*\b\d+\s*(hours?|days?|minutes?|hrs?)",
                r"what happened.{0,15}\blast\s+\d+\s*(hours?|days?|hrs?)",
                r"elaborate on the (past|last) \d+ (hours?|days?|hrs?)",
                r"\b(summary|overview|recap|rundown|digest)\s+(of\s+)?(the\s+)?(past|last)\s+\d+\s*(hours?|days?|minutes?|hrs?|weeks?)\b",
                r"\b(summary|overview|recap|rundown)\s+(of\s+)?(all\s+)?(user\s+)?(interactions?|conversations?|chat|activity|messages?|chatter)\b",
                r"\b(can|could|would)\s+(i|you)\s+(get|give|have)\s+(me\s+)?(a\s+)?(summary|recap|overview|rundown)\b",
                r"\b(summarize|recap)\b.*?\b(past|last)\s+\d+\s*(hours?|days?|minutes?|hrs?|weeks?)\b",
                r"\b(past|last)\s+\d+\s*(hours?|days?|hrs?)\s+(of\s+)?(chat|chatter|messages?|activity|interactions?|conversations?)\b",
                r"summarize (all\s+)?(user\s+)?(recent|the last|today'?s?|past)?\s*(interactions?|conversations?|chat|activity|messages?|chatter)",
                r"what have you been (doing|up to)",
                r"recall the last \d+",
                r"\b(get|give)\s+(me\s+)?a\s+recap\b",
                r"\brecap (the|this)?\s*(thread|conversation|chat|channel)\b",
                r"what('s| has| have) been (going on|happening)",
                r"what did (i|we|you|people|everyone) (miss|talk about)",
                r"catch me up",
                r"what'?s been said",
                # Channel-scoped recall — "anything aware of from kaia-opolis", "summary of #general chatter"
                r"\b(summary|recap|overview)\s+of\s+(#?\w[\w-]*|\<#\d+\>).*(chatter|chat|messages?|conversations?|activity)\b",
                r"(anything|something).{0,20}(aware of|know about|should know).{0,20}(from|in)\s+\w",
                r"(what|anything).{0,20}(going on|happening|discussed|said).{0,20}(in|from)\s+\w",
            ],
            "SUMMARIZATION": [
                r"^\s*(kaia\s+)?(summarize|summary of|digest|tl;?dr)\b",
                r"\b(give me a summary|brief on|overview of|breakdown of|tell me about the (?:file|article|doc|paper|whitepaper)|what does .*? say)\b",
                r"\b(can you|please|could you)\s+(summarize|give a summary|break down|explain the file)\b",
                r"\b(tell me about|what is in)\s+[\w\-]+?\.(?:md|txt|pdf|docx|json|yaml)\b",
            ],
            "SYNTHESIS_SCAN": [
                r"\b(headlines|current events|happening today|latest on)\b",
                r"^\s*(kaia\s+)?(what's the|any) news\b",
                r"^\s*(kaia\s+)?what's happening in the (world|news)\b",
                r"\b(anything new (with|about))\b",
                r"\b(latest updates?)\b",
                # "recent Iran war news", "tech news", "news about the strikes".
                # A bare "news" is not enough: "that's good news" is not a request.
                r"\b(recent|latest|today'?s|current|world|political|politics|tech|hacker|breaking)\b.{0,30}\bnews\b",
                r"\bnews\s+(on|about|from|regarding)\b",
            ],
            "TECH_INQUIRY": [
                r"\b(how do i|how to|explain|what is)\s+(python|nvidia|cuda|gpu|linux|terminal|code|script)\b",
                r"\b(command for|check usage|process list)\b"
            ]
        }
        
        # News is checked before PRECISE_RECALL. Triggers are tried in order and
        # the first match wins, and "tell me about" is a PRECISE_RECALL cue — so
        # "Kaia, tell me about recent hacker news" was routed as a question
        # about herself, identity-scoped, and answered from her own logs.
        order = list(raw_triggers)
        order.remove("SYNTHESIS_SCAN")
        order.insert(order.index("PRECISE_RECALL"), "SYNTHESIS_SCAN")
        for strategy in order:
            self.fast_triggers[strategy] = [re.compile(p, re.IGNORECASE) for p in raw_triggers[strategy]]

        log_success("IntentParser initialized (regex fast-path only).")
    
    def fast_parse(self, query: str) -> Optional[Intent]:
        """Layer 1: Fast Pattern Detection"""
        # A pasted URL is not the question: its path words ("status",
        # "system", "debug") matched intents on every shared link.
        query_lower = re.sub(r"https?://\S+", " ", query).lower().strip()
        # "Kaia, <link>" is sharing the link, not saying hello; the greeting
        # shortcut would skip retrieval for it.
        if query_lower != query.lower().strip() and re.fullmatch(r"\W*(kaia)?\W*", query_lower):
            return None
        
        # Fast-path for explicit file/document review intent.
        # Fix #10: Only match explicit file-reference phrases and extensions to avoid
        # shadowing DIAGNOSTIC_DEEP_DIVE for queries like "check the log file" or
        # "check the error". Generic words like "file"/"doc" are intentionally excluded.
        _FILE_REVIEW_CUES = ["take a look at", "looked at", "read the", "seen the", "go over"]
        _FILE_EXTENSIONS = [".md", ".txt", ".pdf", ".docx"]
        # Compound noun phrases that unambiguously refer to a document (not a system file/log)
        _FILE_COMPOUND_PHRASES = ["research file", "research doc", "research report",
                                   "setup research", "setup file", "setup doc",
                                   "aquarium research", "planning doc", "planning report"]
        if any(phrase in query_lower for phrase in _FILE_REVIEW_CUES):
            if (any(ext in query_lower for ext in _FILE_EXTENSIONS)
                    or any(phrase in query_lower for phrase in _FILE_COMPOUND_PHRASES)):
                log_debug("Fast-path trigger: PRECISE_RECALL (file review request)")
                return Intent(
                    explicit_intent="file review request",
                    implied_needs=["knowledge retrieval"],
                    emotional_context="neutral",
                    temporal_focus="present",
                    relational_context="general",
                    suggested_strategy="PRECISE_RECALL",
                    confidence=0.80  # Lowered slightly to let LLM override if context differs
                )

        for strategy, patterns in self.fast_triggers.items():
            for compiled_re in patterns:
                if compiled_re.search(query_lower):
                    # Guard: SUMMARIZATION triggered by incidental phrases in long
                    # conversational messages (e.g. "overview of phylogenetics").
                    # Real summarization requests are short and directive.
                    if strategy == "SUMMARIZATION" and len(query_lower.split()) > 25:
                        log_debug(f"SUMMARIZATION trigger suppressed: message too long ({len(query_lower.split())} words)")
                        continue

                    log_debug(f"Fast-path trigger: {strategy}")
                    
                    temporal_focus = "past_recent" if strategy == "RECAP_QUERY" else "present_immediate"
                    
                    # Construct a basic Intent object from the trigger
                    return Intent(
                        explicit_intent=query,
                        implied_needs=["immediate_response"],
                        emotional_context="neutral",
                        temporal_focus=temporal_focus,
                        relational_context="direct_command" if "COMMAND" in strategy else "social_casual",
                        suggested_strategy=strategy,
                        confidence=1.0
                    )
        return None

QueryClassifier = IntentParser

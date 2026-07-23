"""
Post-Generation Safety Pipeline & Security Dogtag Replay Logger
================================================================

Consolidates raw LLM post-generation sanitization into a unified, 10-layer testable pipeline (💡-4)
and provides thread-safe verbatim security dogtag replay logging (💡-3).
"""

import os
import re
import time
import json
import threading
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

from utils.infrastructure.logging.kaia_logger import log_info, log_warning, log_debug
from utils.core.hallucination_detector import HallucinationDetector
from utils.core.response_filter import EmergencyContaminationFilter, BotSpeakFilter

_dogtag_replay_lock = threading.Lock()


def log_security_dogtag_replay(
    trigger_type: str,
    query: str,
    raw_response: str,
    matched_rule: str,
    author_id: Optional[int] = None,
    channel_id: Optional[int] = None
):
    """Verbatim prompt and response logger for security dogtag trips (💡-3).
    
    Enables offline J-space replay by recording verbatim query, generated output,
    and the tripped security rule to memory/security_dogtag_replay.jsonl.
    """
    try:
        log_dir = "memory"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "security_dogtag_replay.jsonl")
        
        entry = {
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger_type": trigger_type,
            "matched_rule": matched_rule,
            "author_id": str(author_id or "unknown"),
            "channel_id": str(channel_id or "unknown"),
            "query": query[:500] if query else "",
            "raw_response": raw_response[:1000] if raw_response else ""
        }
        
        with _dogtag_replay_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
                
        log_warning(f"[SECURITY_DOGTAG_REPLAY] Tripped rule '{trigger_type}' ({matched_rule}) — logged for offline replay.")
    except Exception as e:
        log_warning(f"Failed to log security dogtag replay: {e}")


class PostGenerationSafetyPipeline:
    """Unified 10-Layer Post-Generation Safety Pipeline (💡-4)."""

    DANGLING_STUB_PATTERN = re.compile(
        r"^[^.!?]{0,60}(select|choose|pick|say|answer|go with)(?:\s+is|\s+was|\s+would be)?\s*\.\s*$",
        re.IGNORECASE | re.MULTILINE
    )

    @classmethod
    def sanitize_raw_text(cls, text: str) -> str:
        """Apply basic deterministic text cleanups (backticks, time signatures)."""
        if not text:
            return ""
        # 1. Backtick Stripping
        text = text.replace("```", "").replace("``", "")
        # 3. Tracer & Time Signature Stripping
        text = re.sub(r'\[?CURRENT_TIME\]?:?.*', '', text).strip()
        text = re.sub(r'\[?CURRENT_USER\]?:?.*', '', text).strip()
        text = re.sub(
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
            r'(January|February|March|April|May|June|July|August|September|October|November|December)'
            r'\s+\d{1,2},\s+\d{4}\s+\|.*',
            '', text
        ).strip()
        return text

    @classmethod
    def process_attempt(
        cls,
        content: str,
        attempt: int,
        query: str = "",
        author_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        is_channel_recall: bool = False,
        channel_refs: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Run post-generation sanitization layers on a generated turn attempt.
        
        Returns:
            Tuple of (cleaned_content_or_canned_override, rejection_reason).
            If content fails a layer requiring a retry, cleaned_content is None.
        """
        if not content:
            return None, "Empty raw response"

        # Step 1: Backtick Stripping & Step 3: Time Signature Stripping
        content = cls.sanitize_raw_text(content)

        # Step 2: Dangling Stub Detection
        if cls.DANGLING_STUB_PATTERN.search(content) and len(content.strip()) < 120:
            log_warning(f"Attempt {attempt}: Dangling stub detected after stripping.")
            return None, "Dangling stub detected"

        # Step 4: Empty Response Verification
        if not content or not content.strip():
            return None, "Empty content after basic sanitization"

        # Step 5: HallucinationDetector
        if HallucinationDetector.contains_hallucination(content):
            log_security_dogtag_replay(
                trigger_type="hallucination_detector",
                query=query,
                raw_response=content,
                matched_rule="contains_hallucination",
                author_id=author_id,
                channel_id=channel_id
            )
            cleaned = HallucinationDetector.clean_response(content)
            if not cleaned or not cleaned.strip():
                return None, "Stripped by HallucinationDetector"
            content = cleaned

        # Step 6: EmergencyContaminationFilter
        filtered_contamination = EmergencyContaminationFilter.filter_response(content)
        if not filtered_contamination:
            log_security_dogtag_replay(
                trigger_type="emergency_contamination_filter",
                query=query,
                raw_response=content,
                matched_rule="contamination_or_affect_spam",
                author_id=author_id,
                channel_id=channel_id
            )
            return None, "Emergency contamination / fiction detected"
        content = filtered_contamination

        # Step 7: BotSpeak Filter
        filtered_botspeak = BotSpeakFilter.strip_bot_speak(content)
        if not filtered_botspeak or not filtered_botspeak.strip():
            return None, "Completely stripped by BotSpeakFilter"
        content = filtered_botspeak

        # Step 8: Channel Recall Fabrication Guard
        if is_channel_recall and channel_refs:
            fab_found = False
            for ch in channel_refs:
                fab_patterns = [
                    re.compile(rf'(from|within|in|regarding|about|per)\s+{re.escape(ch)}\b[,:]', re.IGNORECASE),
                    re.compile(rf'{re.escape(ch)}\s*[:,]\s*(the|a|there|primary|notable|key|main)', re.IGNORECASE),
                ]
                for fp in fab_patterns:
                    if fp.search(content):
                        fab_found = True
                        log_security_dogtag_replay(
                            trigger_type="channel_recall_fabrication",
                            query=query,
                            raw_response=content,
                            matched_rule=f"fabricated_attribution:{ch}",
                            author_id=author_id,
                            channel_id=channel_id
                        )
                        break
                if fab_found:
                    break
            if fab_found:
                log_warning(f"Attempt {attempt}: Channel-recall fabrication detected. Returning canned honest response.")
                canned_response = (
                    "i don't have clear records from those channels right now. "
                    "my logs don't track channel-specific activity yet — "
                    "i can tell you what i've picked up from our conversations, "
                    "but i can't give you a reliable summary of what happened in specific channels."
                )
                return canned_response, None

        return content, None

    @classmethod
    def apply_style_collapsers(cls, text: str) -> str:
        """Step 10: Ellipsis & Em Dash Collapsers (run on final response before send)."""
        if not text:
            return ""

        # Ellipsis Collapser
        frag_count = len(re.findall(r'\w+[\u2026\.]{2,}', text))
        if frag_count >= 3:
            log_warning(f"[ELLIPSIS_COLLAPSE] Collapsing {frag_count} ellipsis fragments in output")
            text = re.sub(r'(\w)[\u2026\.]{2,}\s+', r'\1. ', text)
            text = re.sub(r'(\w)[\u2026\.]{2,}$', r'\1.', text, flags=re.MULTILINE)
            text = re.sub(r'^\s*[\u2026\.]{2,}\s*$', '', text, flags=re.MULTILINE)
            text = re.sub(r'\.{2,}', '.', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.strip()

        # Em Dash Collapser
        em_dash_count = text.count('\u2014')
        if em_dash_count >= 3:
            log_warning(f"[EM_DASH_COLLAPSE] Collapsing {em_dash_count} em dashes in output")
            text = re.sub(r'(\w)\u2014(\w)', r'\1, \2', text)
            text = re.sub(r'(\w)\u2014\s+', r'\1. ', text)
            text = re.sub(r'\s+\u2014(\w)', r'. \1', text)
            text = re.sub(r'\u2014', ', ', text)
            text = re.sub(r'[,\.]\s*[,\.]', '.', text)
            text = re.sub(r'\s{2,}', ' ', text)

        return text

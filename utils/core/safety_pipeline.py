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

    # ------------------------------------------------------------------
    # Sept 1-5 2026 persona audit. These two guards need the *user's query*
    # to make their decision, so they live here rather than in BotSpeakFilter.
    # ------------------------------------------------------------------

    # A quoted span, matched as an explicit open/close PAIR. Pairing matters: a single
    # character class would let the apostrophe in "starkind's" close the span early.
    QUOTED_SPAN = re.compile(
        '\u201c([^\u201d\u201c]{12,300})\u201d'      # curly double
        '|"([^"]{12,300})"'                    # straight double
        "|\u2018([^\u2019\u2018]{12,300})\u2019"     # curly single
    )

    # Markers that the user is joking, exaggerating or posting a meme rather than
    # reporting a real physical emergency.
    SATIRE_MARKERS = re.compile(
        r"\blol\b|\blmao\b|\bhaha\b|\bjk\b|/s\b|\bi'?m sure that'?s normal\b"
        r'|\bsimply inspirational\b|:\)|\ud83d\ude02|\ud83d\ude05|\ud83d\udc4c|\ud83e\udd23'
        r'|\bhttps?://\S*(?:reddit|imgur|tenor|giphy|9gag|knowyourmeme)\S*'
        r'|\.(?:gif|png|jpg|jpeg|webp)\b',
        re.IGNORECASE
    )

    # Physical-emergency directives that must not be issued off a joke.
    EMERGENCY_DIRECTIVES = re.compile(
        r'\bunplug\s+(?:it|the\s+\w+)\s+immediately\b'
        r'|\bdecidedly\s+not\s+normal\b'
        r'|\bpotential\s+for\s+real[- ]world\s+harm\b'
        r'|\bthermal\s+combustion\b'
        r'|\bbefore\s+you\s+(?:potentially\s+)?(?:cause|scorch|start)\b'
        r'|\bcall\s+emergency\s+services\b'
        r'|\bare\s+you\s+in\s+(?:immediate\s+)?danger\b'
        r'|\bthis\s+is\s+not\s+appropriate\s+behaviou?r\b',
        re.IGNORECASE
    )

    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r'[^a-z0-9 ]+', ' ', (s or '').lower())

    @classmethod
    def strip_prompt_echo(cls, content: str, query: str) -> str:
        """P1b — remove quoted spans that merely replay the user's own message.

        The audited failure mode opened a turn by quoting the user back at themselves
        ("\u201cstarkind\u2019s assessment\u2026\u201d yes, you\u2019re largely summarizing his point"), often several
        times per turn. A quoted span is dropped only when most of its words actually
        appear in the user's message, so genuine quotation of an article or a third
        party survives untouched.
        """
        if not content or not query:
            return content
        qnorm = set(cls._norm(query).split())
        if len(qnorm) < 3:
            return content

        def _repl(m):
            span = next((g for g in m.groups() if g), None)
            if span is None:
                return m.group(0)
            words = [w for w in cls._norm(span).split() if len(w) > 2]
            if len(words) < 3:
                return m.group(0)
            overlap = sum(1 for w in words if w in qnorm) / len(words)
            if overlap >= 0.7:
                log_warning(f"[PROMPT_ECHO_GUARD] Dropped echoed span: '{span[:60]}...'")
                return ''
            return m.group(0)

        cleaned = cls.QUOTED_SPAN.sub(_repl, content)
        if cleaned == content:
            return content
        # Tidy the punctuation the removed span left behind.
        cleaned = re.sub(r'^[\s,.\u2013\u2014-]+', '', cleaned)
        # Horizontal whitespace only: r'\s{2,}' also matches newline runs and would
        # collapse every paragraph break in the response into a single space.
        cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s+([,.!?;:])', r'\1', cleaned)
        cleaned = re.sub(r'(?:(?<=^)|(?<=[.!?]\s))\s*[,;:]\s*', '', cleaned)
        return cleaned.strip()

    @classmethod
    def guard_literalism(cls, content: str, query: str) -> Optional[str]:
        """P4 — refuse to answer obvious hyperbole or a meme as a physical emergency.

        Returns None when the response is acceptable, or a rejection reason when the
        user was plainly joking and the model still issued emergency directives. The
        caller retries; a retry is right here because the correct reply is a different
        reading of the message, not a redacted version of the wrong one.
        """
        if not content or not query:
            return None
        if not cls.SATIRE_MARKERS.search(query):
            return None
        if cls.EMERGENCY_DIRECTIVES.search(content):
            return "Literal-emergency reading of a joking or meme message"
        return None

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
        # Internal scrape/directive envelopes must never reach the user (P6).
        text = re.sub(r'\[\s*SYSTEM\s+WARNING\b[^\]]*\]', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
        text = re.sub(r'\[\s*CORE_DIRECTIVE\b[^\]]*\]', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
        # Step 1.5: Thought/Monologue JSON Leak Scrubber
        # Catches raw inner monologue bleed like {"thought": "i wonder if..."}
        text = re.sub(r'\{?\s*"thought"\s*:\s*"[^"]*"\s*\}?', '', text).strip()
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

        # Step 7.5: Prompt-echo guard (P1b) and satire-literalism guard (P4).
        # Both need the user's query, so they run here rather than inside BotSpeakFilter.
        echoed = cls.strip_prompt_echo(content, query)
        if echoed != content:
            if not echoed or not echoed.strip():
                return None, "Response was entirely an echo of the user's message"
            content = echoed

        literalism = cls.guard_literalism(content, query)
        if literalism:
            log_security_dogtag_replay(
                trigger_type="satire_literalism",
                query=query,
                raw_response=content,
                matched_rule="emergency_directive_on_joking_input",
                author_id=author_id,
                channel_id=channel_id
            )
            return None, literalism

        # Step 8: Channel Recall Fabrication Guard
        if is_channel_recall and channel_refs:
            fab_found = False
            for ch in channel_refs:
                ch_clean = ch.lstrip('#')
                fab_patterns = [
                    re.compile(rf'(from|within|in|regarding|about|per)\s+#?{re.escape(ch_clean)}\b[,:]', re.IGNORECASE),
                    re.compile(rf'#?{re.escape(ch_clean)}\s*[:,]\s*(the|a|there|primary|notable|key|main)', re.IGNORECASE),
                    re.compile(rf'channel\s+#?{re.escape(ch_clean)}\b\s*:', re.IGNORECASE),
                    re.compile(rf'#{re.escape(ch_clean)}\s*:', re.IGNORECASE),
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

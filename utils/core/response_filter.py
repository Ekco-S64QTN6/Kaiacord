import re
from typing import List, Optional
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_warning

class HallucinationDetector:
    """Detect and prevent hallucination feedback loops"""
    
    HALLUCINATION_PATTERNS = [
        # Structural leaks
        r"<recorded_knowledge",
        r"</recorded_knowledge>",
        r"\[INTERNAL REFLECTION",
        r"\[CONVERSATION HISTORY",
        r"\[IDENTITY CORE",
        r"\b(rag (nodes?|context|results?)|retrieval (system|archives?|nodes?))\b",
        r"\btunable (parameters?|filters?)\b",
        r"\baid\s*\d+\b",
        r"\bcontext (window|limits?|optimized?)\b",
        
        # High-confidence news/biographical fiction patterns
        r"joint\s+research\s+paper\s+on\s+['\"]?Quantum\s+Consciousness['\"]?",
        r"co-authored\s+by\s+Steve\s+Jobs",
        r"In\s+a\s+shocking\s+turn\s+of\s+events",
        r"Breaking\s+news:?\s+.*?returns\s+to",
        r"^Reports\s+are\s+coming\s+in\s+that",
        r"i\s+remember\s+back\s+in\s+\d{4}\s+when\s+i\s+was",
        
        # Session-specific high-confidence hallucinations (Tracer Terms)
        r"\bThe State of Streaming Services\b",
        r"\bChain of Suspicion\b",
        r"Tenno\s+Heika",
        r"Di\s+Shang",
        r"Cosmic\s+Sociology\s+spell",
        r"\bDeath\s+Squared\b",
        r"\bmouse\s+population\s+caloric\s+restriction\b",
        
        # Fabricated Claims about Grounding
        r"\b(there's|i have) a(n actual)? thread (titled|about|named) ['\"]?(.+?)['\"]?\b",
        r"\b(i remember|my notes mention) a (conversation|outage) (from|last) (.+?)\b",

        # Admitted Fabrications
        r"\b(my memory is faulty|was a fabrication|mimicking a conversational style|placeholder for a topic)\b",
        r"\b(sorry for the confusion|extrapolating from my general observations|no actual thread with that title)\b",
        r"\b(memory's\s+a\s+bit\s+hazy|double-check\s+the\s+records|was\s+recalling\s+the\s+wrong\s+study)\b"
    ]
    
    _compiled_pattern = re.compile("|".join(HALLUCINATION_PATTERNS), re.IGNORECASE)

    @classmethod
    def contains_hallucination(cls, text: str) -> bool:
        """Check if text contains known hallucination patterns"""
        return bool(cls._compiled_pattern.search(text))
    
    @classmethod
    def clean_response(cls, response: str) -> str:
        """Remove hallucinated content from response"""
        if not cls.contains_hallucination(response):
            return response
        
        # Split into lines and filter out hallucinated ones
        lines = response.split('\n')
        clean_lines = []
        
        for line in lines:
            if not cls.contains_hallucination(line):
                clean_lines.append(line)
            else:
                # Replace hallucinated line with something neutral
                clean_lines.append("...")  # Or empty line
        
        # If we removed too much, signal failure by returning None
        clean_response = '\n'.join(clean_lines).strip()
        
        if not clean_response:
            return None
        
        return clean_response

class EmergencyContaminationFilter:
    """Emergency filter to prevent specifically fake-sounding news prose or hallucinations."""
    
    CONTAMINATION_PATTERNS = [
        r"this\s+fictional\s+account",
        r"according\s+to\s+a\s+news\s+report\s+i\s+saw",
        r"latest\s+update\s+indicates\s+that\s+.*?\s+(is|has)\s+been\s+discovered",
        r"(joint\s+)?research\s+paper\s+on\s+['\"]?Quantum\s+Consciousness['\"]?",
        r"co-authored\s+(a\s+paper\s+)?by\s+Steve\s+Jobs",
        r"Steve\s+Jobs\s+co-authored",
        r"In\s+a\s+shocking\s+turn\s+of\s+events",
        r"Breaking\s+news:?",
        r"\b(the state of streaming services|chain of suspicion)\b", # Tracer contamination
    ]

    VERACITY_FALLBACK = "wait, scratch that. something about my memory's a bit hazy on the specifics of that. i'd have to double-check the records to be sure."
    RETRY_THRESHOLD = 0.5  # If more than 50% lines contaminated, retry
    
    _compiled_pattern = re.compile("|".join(CONTAMINATION_PATTERNS), re.IGNORECASE)

    @classmethod
    def filter_response(cls, response: str) -> Optional[str]:
        """Remove ANY contamination from response. If too much is removed, return None to trigger retry."""
        if not response:
            return None

        lines = response.split('\n')
        filtered_lines = []
        contaminated_count = 0
        contamination_found = False
        for line in lines:
            # Skip lines with contamination
            if cls._compiled_pattern.search(line):
                contamination_found = True
                contaminated_count += 1
                continue
            
            filtered_lines.append(line)
        
        if contamination_found:
            log_warning(f"[VERACITY GUARD] Removed {contaminated_count} contaminated lines.")
        
        if contamination_found and len(filtered_lines) <= (len(lines) * (1 - cls.RETRY_THRESHOLD)):
            # If the "fiction" exceeded the threshold, signal a full retry
            log_warning(f"[VERACITY GUARD] Too much contamination (threshold {cls.RETRY_THRESHOLD}). Triggering full retry.")
            return None
            
        filtered_response = '\n'.join(filtered_lines).strip()
        
        # If we removed everything, signal retry
        if not filtered_response:
            return None
        
        return filtered_response
    
    @staticmethod
    def expand_news_query(query: str) -> List[str]:
        """
        Expand a news query with related terms for broader RAG retrieval.
        Returns a list of query variations.
        """
        # For now, return empty to prevent aggressive news fetching on simple 'whats new'
        # unless explicit news keywords are present.
        keywords = ['news', 'latest', 'headlines', 'world', 'tech']
        if any(k in query.lower() for k in keywords):
            return [f"{query} latest news", f"{query} updates"]
        return []
    
    
class BotSpeakFilter:
    """
    Minimal filter to catch only the most egregious system leaks.
    Most behavioral constraints should be handled by the Persona prompt.
    """
    
    # Strip roleplay actions only — targeted patterns to avoid legitimate content
    RE_PARENS = re.compile(r'\((?![0-9]{4})([^\)]+?)\)', re.IGNORECASE)
    RE_ASTERISKS = re.compile(r'(?<!\*)\*(?!\*)([^\*]+?)\*(?!\*)', re.IGNORECASE)
    RE_PREFIXES = re.compile(r'^(Kaia|User|Assistant|System):\s*', re.IGNORECASE | re.MULTILINE)
    
    # Anti-engagement bait patterns (robotic assistant questions)
    BAIT_PATTERNS = [
        r"what('s|\s+is)\s+on\s+your\s+mind\??",
        r"what\s+(are|is|were)\s+you\s+(working\s+on|up\s+to|doing)[^.!?]*\??",
        r"any\s+thoughts\??",
        r"do\s+you\s+have\s+any\s+questions\??",
        r"let\s+me\s+know\s+if\s+you\s+need\??",
        r"how\s+can\s+i\s+(help|assist)\??",
        r"why\?", # Standalone "Why?" often feels bait-y
        r"what(’|')s\s+driving\s+your\s+interest\??",
        r"you\s+following\s+anything\s+specific\??",
        r"what\s+do\s+you\s+(think|need)\??",
        r"anything\s+else\??",
        r"what\s+(about|echoes?|threads?)\s+(do\s+)?(you|your)\b[^.!?]*\??",
        r"what'?s\s+the\s+(core|biggest|main|primary|hardest|toughest)\s+\w+[^.!?]*\??",
        r"what'?s\s+(your|the)\s+\w+\s+(task|hurdle|challenge|goal|obstacle|plan)[^.!?]*\??",
        r"how\s+(are\s+you\s+|do\s+you\s+)(approaching|handling|dealing|feeling)[^.!?]*\??",
        r"(facing|dealing\s+with)\s+(right\s+now|currently)[^.!?]*\??",
        r"achieving\s+that\s+\w+[^.!?]*\??",
    ]
    
    SYSTEM_PROSE_PATTERNS = [
        r"As\s+an\s+AI\s+language\s+model",
        r"As\s+an\s+AI",
        r"I\s+am\s+programmed\s+to",
        r"my\s+knowledge\s+cutoff",
        r"I\s+don't\s+have\s+personal\s+opinions",
        r"How\s+can\s+I\s+help\s+you\s+today\?",
        r"\b(sentient\s+)?digital\s+entity\b",
        r"\b(simulation|construct|recalibrate|parsing\s+routines?)\b",
    ]
    
    # Precompiled combined patterns for efficiency
    RE_BAIT = re.compile("|".join(BAIT_PATTERNS), re.IGNORECASE)
    RE_SYSTEM_PROSE = re.compile("|".join(SYSTEM_PROSE_PATTERNS), re.IGNORECASE)
    RE_TRAILING_USER_QUESTION = re.compile(
        r'(?<![?])\s*((?:and\s+)?(?:what|how|why|where|when|who|which|do\s+you|are\s+you|have\s+you|can\s+you|would\s+you|could\s+you|did\s+you|is\s+there|isn\'t|aren\'t)[^.!?\n]{3,}\?)\s*$',
        re.IGNORECASE
    )
    
    ACTION_VERBS = {
        'nods', 'sighs', 'grins', 'smiles', 'laughs', 'pauses', 'frowns', 'shrugs', 
        'blinks', 'tilts', 'leans', 'taps', 'looks', 'waves', 'winks', 'checks', 
        'points', 'whispers', 'mumbles', 'groans', 'hisses', 'pouts', 'scoffs',
        'types', 'adjusts', 'swallows', 'stares', 'recalibrates', 'processes'
    }

    @classmethod
    def _selective_strip(cls, match):
        """Callback to strip markers and decide if content is an action or emphasis."""
        content = match.group(1).strip()
        clean_content = content.lower().rstrip('.?!… ')
        
        # Heuristic: If it's a known action verb, strip it.
        if clean_content in cls.ACTION_VERBS:
            return ''
            
        # If it's a multi-word phrase that looks like roleplay (e.g. *scratches head*)
        # We check if it's all lowercase and doesn't contain numbers.
        if ' ' in clean_content:
            is_roleplay = all(word.islower() for word in clean_content.split() if word.isalpha())
            has_no_numbers = not any(char.isdigit() for char in clean_content)
            if is_roleplay and has_no_numbers:
                return ''
        
        # Otherwise, assume it's emphasis and keep the word but remove the markers.
        return content

    @classmethod
    def harden(cls, text: str) -> str:
        """Apply all hardening filters to the text to strip roleplay and preserve emphasis."""
        if not text:
            return text
            
        cleaned = text
        last_cleaned = None
        
        # Repetitive cleaning until no more patterns match (handles nested/adjacent)
        while cleaned != last_cleaned:
            last_cleaned = cleaned
            
            # 1. Selective stripping for parens and asterisks
            cleaned = cls.RE_PARENS.sub(cls._selective_strip, cleaned)
            cleaned = cls.RE_ASTERISKS.sub(cls._selective_strip, cleaned)
            
            # 2. Strip standalone role prefixes
            cleaned = cls.RE_PREFIXES.sub('', cleaned)
            
            # Clean up empty markers like () or ** that might remain
            cleaned = re.sub(r'\(\s*\)', '', cleaned)
            cleaned = re.sub(r'(?<!\*)\*\s*\*(?!\*)', '', cleaned)
            
            # Clean up resulting double spaces or empty lines
            cleaned = re.sub(r' +', ' ', cleaned)
            cleaned = re.sub(r' ([\.,\?\!])', r'\1', cleaned)
            
            # Global cleanup for any remaining role prefix remnants
            cleaned = re.sub(r'^\s*(Kaia|User|Assistant):\s+', '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
            
            cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)
            cleaned = cleaned.strip()
        
        # 3. Strip system prose (Single Pass)
        cleaned = cls.RE_SYSTEM_PROSE.sub('', cleaned)

        # 4. Final Pass: Strip robotic engagement bait
        cleaned = cls.strip_trailing_questions(cleaned)
        
        return cleaned

    @classmethod
    def strip_trailing_questions(cls, text: str) -> str:
        """Strip robotic engagement bait questions from the end of the response."""
        if not text:
            return text
            
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            current_line = line
            stripped = line.strip()
            if not stripped:
                clean_lines.append(line)
                continue
            
            # Keep stripping while the line ends with a bait pattern
            while True:
                found_bait = False
                # Match pattern specifically at the end of the line
                match = cls.RE_BAIT.search(current_line)
                if match:
                    span = match.span()
                    remaining = current_line[span[1]:].strip(' .?!…')
                    if not remaining:
                        # It's at the end!
                        removed = current_line[span[0]:].strip()
                        current_line = current_line[:span[0]].rstrip(' ')
                        
                        if current_line:
                            if not any(p in removed.lower() for p in ["coffee's brewing", "pixel's chirping"]):
                                log_warning(f"[BAIT_GUARD] Truncated robotic question: '{removed}'")
                            found_bait = True
                            continue # Check for more bait on the same line
                        else:
                            # The entire line was bait!
                            current_line = ""
                            found_bait = True
                
                if not found_bait or not current_line:
                    break
            
            if current_line:
                clean_lines.append(current_line)
            else:
                # If the whole line was bait, we drop it unless it's the only line
                if len(lines) > 1:
                    log_warning(f"[BAIT_GUARD] Dropped full-bait line: '{line}'")
                    continue
                else:
                    # If it's the only line, we now allow it to be dropped
                    # This allows the self-healing loop to trigger a retry
                    log_warning(f"[BAIT_GUARD] Dropped single-line bait: '{line}'")
                    continue
                    
        result = "\n".join(clean_lines).strip()

        # --- Pass 2: structural check — strip any user-directed question at the very end ---
        # Catches novel phrasing like "What echoes do you carry?" that regex can't anticipate.
        # Splits on sentence boundaries, checks if the final sentence is a question to the user.
        if result:
            # Split into sentences (naive but sufficient — we only care about the last one)
            sentences = re.split(r'(?<=[.!?])\s+', result)
            if len(sentences) > 1:
                last = sentences[-1].strip()
                # Is it a question directed at the user?
                if (last.endswith('?') and 
                    re.search(r'\b(you|your|yours)\b', last, re.IGNORECASE) and
                    not re.search(r'\b(that|it|this|the|a|an)\b\s+\?', last, re.IGNORECASE)):  # avoid stripping rhetorical "is that right?"
                    log_warning(f"[BAIT_GUARD] Stripped user-directed trailing question: '{last}'")
                    result = ' '.join(sentences[:-1]).strip()

        return result

    @classmethod
    def strip_bot_speak(cls, text: str) -> str:
        """Alias for harden for backward compatibility."""
        return cls.harden(text)

    @classmethod
    def harden_title(cls, text: str) -> str:
        """Light hardening for short text like thread titles.
        
        Skips the aggressive paren/asterisk roleplay stripping that can
        destroy legitimate words in short text. Only applies prefix removal
        and basic cleanup.
        """
        if not text:
            return text
        
        cleaned = text
        
        # Strip role prefixes
        cleaned = cls.RE_PREFIXES.sub('', cleaned)
        
        # Strip only obvious roleplay markers: standalone action verbs in asterisks
        # but preserve parenthetical content (often contains essential words)
        for verb in cls.ACTION_VERBS:
            cleaned = re.sub(rf'\*{verb}\*', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up whitespace
        cleaned = re.sub(r'  +', ' ', cleaned)
        cleaned = cleaned.strip()
        
        return cleaned


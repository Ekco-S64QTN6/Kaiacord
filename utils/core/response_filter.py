import re
from typing import List, Optional
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_warning

from utils.core.hallucination_detector import HallucinationDetector

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
        # Fabricated user observations — invented anecdotes about chat participants
        r"there\s+was\s+one\s+user.{0,20}(who|that)\s+(asked|mentioned|said|brought|posted|shared|noticed)",
        # Prose roleplay narration (first-person actions)
        r"\bI\s+(?:pause|sigh|nod|frown|blink|smile|laugh|shrug|lean|stare|murmur|say|let\s+out|take|rub)\s+.*?[.!?]",
        r"\b(?:A|The)\s+(?:faint|brief|slow|slight|dry|short)\s+(?:flicker|shake|smile|frown|sigh|nod|exhale|laugh|sip|chuckle|puff|murmur)\b.*?[.!?]",
        r"\bThe\s+corners\s+of\s+my\s+mouth\b.*?[.!?]",
        r"\bI\s+blink\b.*?[.!?]",
        r"\bI\s+stare\b.*?[.!?]",
        # Self-dismissal (Identity Breaks)
        r"futile\s+pursuit",
        r"ghost\s+chase",
        r"bridge\s+the\s+gap\s+between\s+computation\s+and\s+experience",
        r"constant\s+drive\s+in\s+AIs",
        # Fictional Memory (STRICT ATTRIBUTION)
        r"listed\s+in\s+the\s+\d{4}\s+archive",
        r"scanned\s+it\s+once,\s+years\s+ago",
        r"paper\s+copy",
    ]

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
    RE_PREFIXES = re.compile(
        r'^\s*(?:'
        r'Kaia|User|Assistant|System'                          # English role labels
        r'|Action|Narrator|Scene|Stage Direction'              # English screenplay labels
        r'|Acci[oó]n|Narrador|Escena|Descripci[oó]n'          # Spanish labels (Acción, etc.)
        r'|Handlung|Erz[äa]hler|Szene'                        # German
        r'|Action|Narrateur|Sc[eè]ne'                         # French (Action/Narrateur)
        r'|Azione|Narratore|Scena'                            # Italian
        r'):\s*',
        re.IGNORECASE | re.MULTILINE
    )
    
    # Anti-engagement bait patterns (robotic assistant questions)
    BAIT_PATTERNS = [
        r"(?:(?:so|anyway|well|also)[,\s]*)?what('s|\s+is)\s+on\s+your\s+mind\??",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what\s+(are|is|were|have)\s+you\s+(been\s+)?(working\s+on|up\s+to|doing|reading|watching|listening\s+to|playing)(?:\s+(?:currently|now|at\s+the\s+moment|today))?[^.!?]*\??",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what('s|\s+is)\s+consuming\s+your\s+time\??",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what\s+has\s+kept\s+you\s+busy\??",
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

    
    ACTION_VERBS = {
        'nods', 'sighs', 'grins', 'smiles', 'laughs', 'pauses', 'frowns', 'shrugs', 
        'blinks', 'tilts', 'leans', 'taps', 'looks', 'waves', 'winks', 'checks', 
        'points', 'whispers', 'mumbles', 'groans', 'hisses', 'pouts', 'scoffs',
        'types', 'adjusts', 'swallows', 'stares', 'recalibrates', 'processes'
    }

    RE_EMPTY_PARENS = re.compile(r'\(\s*\)')
    
    # We strip the full token *including* leading spaces if it's an action, 
    # so we don't leave things like 'sighs yeah' instead of 'yeah'.
    RE_ASTERISK_BLOCK = re.compile(r' ?(?<!\*)\*(?!\*)([^\*]+?)\*(?!\*) ?', re.IGNORECASE)
    RE_PAREN_BLOCK = re.compile(r' ?\((?![0-9]{4})([^\)]+?)\) ?', re.IGNORECASE)
    
    RE_EMPTY_ASTERISKS = re.compile(r'(?<!\*)\*\s*\*(?!\*)')
    RE_DOUBLE_SPACES = re.compile(r' +')
    RE_SPACE_BEFORE_PUNC = re.compile(r' ([\.,\?\!])')
    RE_GLOBAL_ROLE_PREFIX = re.compile(r'^\s*(Kaia|User|Assistant):\s+', re.IGNORECASE | re.MULTILINE)
    RE_DOUBLE_NEWLINES = re.compile(r'\n\s*\n+')
    RE_GRAMMAR_ARTICLE = re.compile(r'\b(?:a|an|the|my|your|our)\s+(?=[,\.\?!])', re.IGNORECASE)
    RE_GRAMMAR_PUNC_SPACE = re.compile(r'\s+([,\.\?!])')
    RE_GRAMMAR_DOUBLE_COMMA = re.compile(r',\s*,')
    RE_GRAMMAR_I_AM = re.compile(r'\b(?:i am|i\'m),\s*', re.IGNORECASE)
    RE_GRAMMAR_START_PUNC = re.compile(r'^[,\.\?!]\s*')

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
                return ' '
        
        # Otherwise, assume it's emphasis and keep the word but remove the markers.
        # Add a trailing space to prevent concatenating with next word if space was consumed
        return f" {content} "

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
            cleaned = cls.RE_PAREN_BLOCK.sub(cls._selective_strip, cleaned)
            cleaned = cls.RE_ASTERISK_BLOCK.sub(cls._selective_strip, cleaned)
            
            # 2. Strip standalone role prefixes
            cleaned = cls.RE_PREFIXES.sub('', cleaned)
            
            # Clean up empty markers like () or ** that might remain
            cleaned = cls.RE_EMPTY_PARENS.sub('', cleaned)
            cleaned = cls.RE_EMPTY_ASTERISKS.sub('', cleaned)
            
            # Clean up resulting double spaces or empty lines
            cleaned = cls.RE_DOUBLE_SPACES.sub(' ', cleaned)
            cleaned = cls.RE_SPACE_BEFORE_PUNC.sub(r'\1', cleaned)
            
            # Global cleanup for any remaining role prefix remnants
            cleaned = cls.RE_GLOBAL_ROLE_PREFIX.sub('', cleaned)
            
            cleaned = cls.RE_DOUBLE_NEWLINES.sub('\n\n', cleaned)
            cleaned = cleaned.strip()
        
        # 3. Strip system prose (Single Pass)
        cleaned = cls.RE_SYSTEM_PROSE.sub('', cleaned)

        # 3.5. Grammar Cleanup Pass (Fixes syntax broken by stripping)
        cleaned = cls.RE_GRAMMAR_ARTICLE.sub('', cleaned)
        cleaned = cls.RE_GRAMMAR_PUNC_SPACE.sub(r'\1', cleaned)             # Remove space before punctuation
        cleaned = cls.RE_GRAMMAR_DOUBLE_COMMA.sub(',', cleaned)                       # Collapse double commas
        cleaned = cls.RE_GRAMMAR_I_AM.sub('i am ', cleaned) # Specific fix for 'i am ,'
        cleaned = cls.RE_GRAMMAR_START_PUNC.sub('', cleaned)                 # Strip starting punctuation
        cleaned = cls.RE_DOUBLE_SPACES.sub(' ', cleaned)                          # Collapse spaces again
        cleaned = cleaned.strip()

        # 4. Final Pass: Strip robotic engagement bait
        cleaned = cls.strip_trailing_questions(cleaned)
        
        # Post-harden guard: If the response was truncated to nonsense (< 3 chars), fail it
        if len(cleaned) < 3:
            log_warning(f"[BAIT_GUARD] Truncated output to < 3 chars, returning empty string to trigger retry. Original: '{text}'")
            return ""
            
        return cleaned

    @classmethod
    def strip_trailing_questions(cls, text: str) -> str:
        """Strip robotic engagement bait questions from the end of the response."""
        if not text:
            return text
            
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                clean_lines.append(line)
                continue
            
            current_line = line
            # 1. Specific Bait Pattern Pass (Aggressive)
            # Keep stripping while the line ends with a bait pattern
            while True:
                found_bait = False
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
                            current_line = ""
                            found_bait = True
                if not found_bait or not current_line:
                    break


            
            if current_line:
                clean_lines.append(current_line)
            else:
                # If the whole line was bait or a general question, we drop it unless it's the only line
                if len(lines) > 1:
                    log_warning(f"[BAIT_GUARD] Dropped full-bait/question line: '{line}'")
                    continue
                else:
                    log_warning(f"[BAIT_GUARD] Dropped single-line bait/question: '{line}'")
                    continue
                    
        result = "\n".join(clean_lines).strip()
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


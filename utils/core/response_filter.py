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
    
    _compiled_pattern = None

    @classmethod
    def contains_hallucination(cls, text: str) -> bool:
        """Check if text contains known hallucination patterns"""
        if cls._compiled_pattern is None:
            combined = "|".join(cls.HALLUCINATION_PATTERNS)
            cls._compiled_pattern = re.compile(combined, re.IGNORECASE)
        
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
    
    @classmethod
    def filter_response(cls, response: str) -> Optional[str]:
        """Remove ANY contamination from response. If too much is removed, return None to trigger retry."""
        if not response:
            return None
            
        lines = response.split('\n')
        filtered_lines = []
        contamination_found = False
        
        for line in lines:
            line_lower = line.lower()
            
            # Skip lines with contamination
            skip_line = False
            for pattern in cls.CONTAMINATION_PATTERNS:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    skip_line = True
                    contamination_found = True
                    log_warning(f"[VERACITY GUARD] Removed contaminated line: {line[:80]}...")
                    break
            
            if not skip_line:
                filtered_lines.append(line)
        
        if contamination_found and len(filtered_lines) <= (len(lines) / 2):
            # If the "fiction" was half or more, signal a full retry
            log_warning("[VERACITY GUARD] Majority of response contaminated. Triggering full retry.")
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
    
    ACTION_VERBS = {
        'nods', 'sighs', 'grins', 'smiles', 'laughs', 'pauses', 'frowns', 'shrugs', 
        'blinks', 'tilts', 'leans', 'taps', 'looks', 'waves', 'winks', 'checks', 
        'points', 'whispers', 'mumbles', 'groans', 'hisses', 'pouts', 'scoffs'
    }

    @classmethod
    def _selective_strip(cls, match):
        """Callback to strip markers and decide if content is an action or emphasis."""
        content = match.group(1).strip()
        clean_content = content.lower().rstrip('.?!… ')
        
        # Heuristic: If it's multiple words or a known action verb, strip it entirely.
        if ' ' in clean_content or clean_content in cls.ACTION_VERBS:
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
        
        return cleaned

    @classmethod
    def strip_bot_speak(cls, text: str) -> str:
        """Alias for harden for backward compatibility."""
        return cls.harden(text)


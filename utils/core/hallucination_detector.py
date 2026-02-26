import re
from typing import Optional
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
    def clean_response(cls, response: str) -> Optional[str]:
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

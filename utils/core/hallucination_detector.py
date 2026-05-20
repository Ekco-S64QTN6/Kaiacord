import re
import json
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
        r"\b(the\s+)?(rag (nodes?|results?)|retrieval (archives?|nodes?))\b",
        r"\btunable (parameters?|filters?)\b",
        r"\baid\s*\d+\b",
        r"\b(my|the model's|the ai's)\s+context (window|limits?|optimized?)\b",
        r"\bmy retrieval (system|archives?|nodes?)\b",
        
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
        r"\bwas\s+recalling\s+the\s+wrong\s+study\b"
    ]
    
    _compiled_pattern = re.compile("|".join(HALLUCINATION_PATTERNS), re.IGNORECASE)

    @classmethod
    def contains_hallucination(cls, text: str) -> bool:
        """Check if text contains known hallucination patterns"""
        return bool(cls._compiled_pattern.search(text))

    @staticmethod
    def log_detection(query: str, response_snippet: str, pattern_matched: str, 
                      confidence: float, action_taken: str):
        """Append a detection event to the rotating hallucination log.
        
        Args:
            query: The user's query that triggered generation.
            response_snippet: First 200 chars of the response that was flagged.
            pattern_matched: The specific pattern or keyword that triggered detection.
            confidence: 0.0–1.0 score. 1.0 = certain hallucination. 0.5 = heuristic catch.
            action_taken: 'cleaned', 'suppressed', 'warned', or 'passed'.
        """
        import os
        log_path = os.path.join("memory", "hallucination_log.jsonl")
        entry = {
            "timestamp": __import__('time').time(),
            "date": __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "query_snippet": query[:100],
            "response_snippet": response_snippet[:200],
            "pattern_matched": pattern_matched,
            "confidence": round(confidence, 3),
            "action_taken": action_taken
        }
        try:
            os.makedirs("memory", exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            # Rotate: keep last 500 entries only (atomic)
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if len(lines) > 500:
                tmp_path = log_path + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-500:])
                os.replace(tmp_path, log_path)
            log_warning(
                f"⚠️ Hallucination Detector: pattern '{pattern_matched}' detected. "
                f"Action taken: {action_taken}."
            )
        except Exception:
            pass  # Never let logging break the main flow

    @classmethod
    def clean_response(cls, response: str, query: str = "") -> Optional[str]:
        """Remove hallucinated content from response"""
        if not cls.contains_hallucination(response):
            return response
        
        # Identify what pattern matched for logging
        match = cls._compiled_pattern.search(response)
        matched_pattern = match.group(0) if match else "unknown"
        
        # Split into lines and filter out hallucinated ones
        lines = response.split('\n')
        clean_lines = []
        
        for line in lines:
            if not cls.contains_hallucination(line):
                clean_lines.append(line)
            # else: Skip contaminated lines to avoid visible artifacts like "..." in the response
        
        # If we removed too much, signal failure by returning None
        clean_response = '\n'.join(clean_lines).strip()
        
        action = "cleaned" if clean_response else "suppressed"
        cls.log_detection(
            query=query if isinstance(query, str) else "",
            response_snippet=response[:200] if response else "",
            pattern_matched=matched_pattern,
            confidence=0.9,
            action_taken=action
        )
        
        if not clean_response:
            return None
        
        return clean_response

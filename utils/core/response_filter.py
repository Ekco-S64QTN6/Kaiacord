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
        
        # High-confidence news/biographical fiction patterns
        r"joint\s+research\s+paper\s+on\s+['\"]?Quantum\s+Consciousness['\"]?",
        r"co-authored\s+by\s+Steve\s+Jobs",
        r"In\s+a\s+shocking\s+turn\s+of\s+events",
        r"Breaking\s+news:?\s+.*?returns\s+to",
        r"^Reports\s+are\s+coming\s+in\s+that",
        r"i\s+remember\s+back\s+in\s+\d{4}\s+when\s+i\s+was",
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
    
    @classmethod
    def clean_response_for_discord(cls, response: str) -> str:
        """
        Remove any user profile data, metadata, or analysis text from responses.
        This prevents Kaia from accidentally including internal profiling data in her chat responses.
        """
        if not response:
            return response
            
        # Split response into lines
        lines = response.split('\n')
        cleaned_lines = []
        
        # Skip any lines that look like user profiles or system metadata
        skip_patterns = [
            'user profile:',
            '## user profile:',
            'updated personalization for',
            '[optimized: saved',
            'interaction indexed',
            'logs indexed:',
            'rag context:',
            'metadata:',
            'nodes retrieved:',
            'quick reference',
            'how to interact with them',
            'shared history & context',
            'their interests & expertise',
            'conversation style notes',
            'relationship status with kaia',
            'potential triggers & sensitivities',
            'growth opportunities'
        ]
        
        in_profile_block = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not in_profile_block:
                    cleaned_lines.append(line)
                continue
                
            line_lower = stripped.lower()
            
            # Check if line starts a profile block or is a metadata line
            is_metadata = any(line_lower.startswith(pattern) for pattern in skip_patterns)
            is_header = stripped.startswith('#') or stripped.endswith(':')
            
            if is_metadata:
                if is_header:
                    in_profile_block = True
                continue
                
            if in_profile_block:
                # Dialogue usually starts with lowercase or common dialogue words
                is_dialogue = stripped[0].islower() or any(line_lower.startswith(w) for w in ["yeah", "no", "well", "i ", "you ", "it's ", "that's "])
                is_bullet = stripped.startswith('- ') or stripped.startswith('* ') or (len(stripped) > 1 and stripped[0].isdigit() and stripped[1] == '.')
                
                if is_dialogue and not is_bullet:
                    in_profile_block = False
                else:
                    # Still in profile block, skip this line
                    continue
            
            if line_lower in [p.strip(':') for p in skip_patterns]:
                continue
            
            # Final check for specific contamination
            if 'Alan Turing' in line and ('mathematician' in line or 'computer scientist' in line):
                continue
            if 'This response was generated' in line or 'The following analysis' in line:
                continue
                
            cleaned_lines.append(line)
        
        # Rejoin lines
        cleaned_response = '\n'.join(cleaned_lines)
        
        # Additional cleanup: Remove any trailing metadata that might have slipped through
        end_markers = ['.', '?', '!', '...', '...']
        for marker in end_markers:
            if marker in cleaned_response:
                last_marker_pos = cleaned_response.rfind(marker)
                if last_marker_pos > len(cleaned_response) * 0.5:
                    next_char = cleaned_response[last_marker_pos + len(marker):].strip()
                    if next_char and not next_char[0].islower():
                        following_text = cleaned_response[last_marker_pos + len(marker):]
                        if any(x in following_text for x in ['User', 'Profile:', 'optimized:', 'Updated']):
                            cleaned_response = cleaned_response[:last_marker_pos + len(marker)]
        
        result = cleaned_response.strip()
        
        if not result:
            return response
        
        return result
    
class BotSpeakFilter:
    """
    Minimal filter to catch only the most egregious system leaks.
    Most behavioral constraints should be handled by the Persona prompt.
    """
    
    # Only strip things that are 100% internal system artifacts that should NEVER be seen.
    # We trust the Persona to handle "As an AI" and other tonal issues.
    FORBIDDEN_PATTERNS = []

    @classmethod
    def harden(cls, text: str) -> str:
        """Apply all hardening filters to the text."""
        # Pass-through for now, unless we find specific critical leaks
        return text

    @classmethod
    def strip_bot_speak(cls, text: str) -> str:
        """
        Deprecated: We now trust the model/persona. 
        This method remains for compatibility but does nothing active.
        """
        return text


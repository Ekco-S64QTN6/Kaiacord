import re
from typing import List, Optional
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_warning

class HallucinationDetector:
    """Detect and prevent hallucination feedback loops"""
    
    HALLUCINATION_PATTERNS = [
        # Structural leaks - indicating the LLM is printing its internal prompt/tags
        r"<external_data_record",
        r"</external_data_record>",
        r"\[INTERNAL REFLECTION",
        r"\[CONVERSATION HISTORY",
        r"\[IDENTITY CORE",
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
    """Emergency filter to prevent ANY fictional content"""
    
    CONTAMINATION_PATTERNS = [
        # Repetitive blacklist approach replaced by structural perspective decoupling.
    ]
    
    @classmethod
    def filter_response(cls, response: str) -> str:
        """Remove ANY contamination from response"""
        if not response:
            return None
            
        lines = response.split('\n')
        filtered_lines = []
        
        for line in lines:
            line_lower = line.lower()
            
            # Skip lines with contamination
            skip_line = False
            for pattern in cls.CONTAMINATION_PATTERNS:
                if re.search(pattern, line_lower):
                    skip_line = True
                    log_warning(f"[EMERGENCY FILTER] Removed contaminated line: {line[:80]}...")
                    break
            
            if not skip_line:
                filtered_lines.append(line)
        
        filtered_response = '\n'.join(filtered_lines).strip()
        
        # If we removed too much, provide a fallback
        if not filtered_response:
            return None
        
        return filtered_response
    
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
    
class ResponseStyleHarden:
    """Programmatically enforce Kaia's persona rules on generated text."""
    
    BAIT_PATTERNS = [
        r"(?i)what('s|\s+is)\s+on\s+your\s+mind\??",
        r"(?i)what\s+are\s+you\s+(working\s+on|up\s+to)\??",
        r"(?i)any\s+thoughts\??",
        r"(?i)do\s+you\s+have\s+any\s+questions\??",
        r"(?i)let\s+me\s+know\s+if\s+you\s+need\??",
        r"(?i)how\s+can\s+i\s+(help|assist)\??",
        r"(?i)why\?",
        r"(?i)what(’|')s\s+driving\s+your\s+interest\??",
        r"(?i)you\s+following\s+anything\s+specific\??",
        r"(?i)what\s+do\s+you\s+(think|need)\??",
        r"(?i)anything\s+else\??",
        r"(?i)(rag\s+classifier|dream\s+fragments?|retrieved\s+nodes?|semantic\s+search|context\s+nodes?)",
    ]

    @classmethod
    def strip_trailing_questions(cls, text: str) -> str:
        """Remove engagement bait questions from the end of a response."""
        if not text:
            return text
            
        lines = text.split('\n')
        if not lines:
            return text
            
        last_line = lines[-1].strip()
        if not last_line:
            return text

        # Split into sentences (simple split)
        # We look for the last sentence
        sentences = re.split(r'(?<=[.!?])\s+', last_line)
        if not sentences:
            return text
            
        # Iteratively remove trailing bait sentences
        modified = False
        while sentences:
            last_sentence = sentences[-1].strip()
            if not last_sentence.endswith('?'):
                break
                
            is_bait = False
            for pattern in cls.BAIT_PATTERNS:
                if re.search(pattern, last_sentence):
                    is_bait = True
                    break
            
            if is_bait:
                sentences.pop()
                modified = True
            else:
                break
        
        if modified:
            new_last_line = " ".join(sentences).strip()
            lines[-1] = new_last_line
            # Rejoin all lines
            return "\n".join(lines).strip()
        
        return text

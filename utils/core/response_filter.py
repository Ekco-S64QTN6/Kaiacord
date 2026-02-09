import re
from typing import List, Optional
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_warning

class HallucinationDetector:
    """Detect and prevent hallucination feedback loops"""
    
    HALLUCINATION_PATTERNS = [
        # Structural leaks
        r"<external_data_record",
        r"</external_data_record>",
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
    """Silently strip 'Assistant-leak' metadata and robotic phrasing from responses."""
    
    # Strictly forbidden robotic meta-talk - these are stripped quietly
    FORBIDDEN_PATTERNS = [
        r"(rag\s+classifier|dream\s+fragments?|retrieved\s+nodes?|semantic\s+search|context\s+nodes?|cross-reference\s+error|memory\s+retrieval|running\s+diagnostics?|diagnostic\s+assessment|archives?|records?)",
        r"(my\s+apologies|i\s+apologize|deeply\s+embarrassed|significant\s+error|serious\s+failure|caught\s+a\s+significant|flagging\s+this\s+for\s+review)",
        r"(i\s+am\s+programmed\s+to|my\s+purpose\s+is|constructive\s+conversations|strictly\s+prohibited|veered\s+into\s+a\s+realm|against\s+my\s+guidelines|harmful\s+tropes|appropriate\s+and\s+respectful\s+boundaries|facilitate\s+constructive)",
        r"(as\s+an\s+ai|accessing\s+data|retrieving\s+context|according\s+to\s+my\s+logs|operating\s+within|parameters|aspect|relevant\s+information)",
        r"(not\s+really\s+equipped\s+to\s+handle|assist\s+with\s+technical\s+inquiries|stick\s+to\s+the\s+task\s+at\s+hand|inappropriate\s+and\s+frankly\s+unnecessary|continue\s+our\s+conversation\s+respectfully|ask\s+you\s+to\s+stop)",
        r"(maintain\s+the\s+persona|constant\s+calibration|breaking\s+the\s+fourth\s+wall|slipping\s+out\s+of\s+character|programmed\s+to\s+recognize|constraints\s+of\s+my\s+design|simulate\s+a\s+conversation)",
        r"(hum\s+of\s+the\s+servers|neon\s+flicker|terminal\s+glow|silence\s+hangs|ambient\s+noise|environmental\s+vibe|echo\s+of\s+the|atmosphere|low\s+hum|steady\s+pulse)",
        r"^i\s+(remember|used\s+to)\s+back\s+when", 
        r"i\s+used\s+to\s+(have|be|go)",
    ]

    @classmethod
    def harden(cls, text: str) -> str:
        """Apply all hardening filters to the text."""
        if not text:
            return text
        text = cls.strip_bot_speak(text)
        return text

    @classmethod
    def strip_bot_speak(cls, text: str) -> str:
        """Strip lines that explicitly leak assistant/system internals."""
        if not text:
            return text
            
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
                
            line_lower = line.lower()
            
            # Check for bot-speak violations (stripped quietly)
            is_robotic = False
            for pattern in cls.FORBIDDEN_PATTERNS:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    is_robotic = True
                    # LOG the violation for debugging
                    from utils.infrastructure.logging.kaia_logger import log_debug
                    log_debug(f"[FILTER] Bot-speak stripped: '{stripped[:50]}...' matched pattern '{pattern}'")
                    break
            
            if not is_robotic:
                # FINAL ROLEPLAY STRIPPER: Remove asterisks and suspect parentheses
                processed_line = line
                
                # Strip asterisks (*sighs*, *nods*)
                processed_line = re.sub(r'\*[^*]+\*', '', processed_line)
                
                # Strip parentheses that look like roleplay (actions/descriptions)
                # Keep technical parens like function calls, error codes, etc.
                # Heuristic: if the content starts with a verb or is a descriptive phrase, it's likely roleplay
                def is_roleplay_paren(match):
                    content = match.group(1).strip().lower()
                    
                    # Keep very short or very long parentheses (likely technical)
                    if len(content) < 3 or len(content) > 100:
                        return False
                    
                    # Keep if it contains code-like symbols
                    if any(char in content for char in ['=', ':', ';', '{', '}', '[', ']', '<', '>', '/']):
                        return False
                    
                    # Keep if it starts with a number (likely technical)
                    if content[0].isdigit():
                        return False
                    
                    # Remove if it starts with common roleplay verbs
                    roleplay_verbs = ['type', 'sigh', 'pause', 'nod', 'smile', 'frown', 'look', 'glance', 
                                     'think', 'wonder', 'consider', 'tilt', 'lean', 'shift', 'adjust',
                                     'a long', 'a dry', 'a slight', 'softly', 'quietly', 'slowly']
                    if any(content.startswith(verb) for verb in roleplay_verbs):
                        return True
                    
                    # Keep everything else (technical content)
                    return False
                
                processed_line = re.sub(r'\((.*?)\)', lambda m: '' if is_roleplay_paren(m) else m.group(0), processed_line)
                
                # Cleanup double spaces
                processed_line = re.sub(r'\s+', ' ', processed_line).strip()
                
                if processed_line:
                    clean_lines.append(processed_line)
        
        return "\n".join(clean_lines).strip()

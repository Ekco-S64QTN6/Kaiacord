#!/usr/bin/env python3
"""
Detector for boilerplate questions at the end of responses
"""
import re

class BoilerplateDetector:
    """Detect and remove boilerplate question endings"""
    
    # Boilerplate questions that should NEVER appear at the end
    BOILERPLATE_ENDINGS = [
        r"what are you working on[.?]?$",
        r"what's on your mind[.?]?$",
        r"anything else on your mind[.?]?$",
        r"what's your take[.?]?$",
        r"seen anything interesting[.?]?$",
        r"got any thoughts[.?]?$",
        r"anything specific you're curious[.?]?$",
        r"yeah\. what's up[.?]?$",
        r"coffee's cold\. what do you need[.?]?$",
        r"i'm here\. what's on your mind[.?]?$",
        r"listening\. go ahead[.?]?$",
        r"not much to say about that\. anything else[.?]?$",
        r"what are you building, really[.?]?$",
        r"what’s it supposed to \*do\*[.?]?$",
        r"what’s the problem, really[.?]?$",
    ]
    
    @classmethod
    def clean_response(cls, response: str) -> str:
        """Remove boilerplate questions from the end of responses.
        
        IMPORTANT: Never returns empty string - if stripping would make response
        empty, return the original response unchanged.
        """
        if not response:
            return response
        
        original_response = response
        lines = response.split('\n')
        clean_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                clean_lines.append(line)
                continue
            
            # Check if this line is a boilerplate question
            is_boilerplate = any(
                re.search(pattern, line_stripped, re.IGNORECASE)
                for pattern in cls.BOILERPLATE_ENDINGS
            )
            
            if not is_boilerplate:
                clean_lines.append(line)
            # else: skip the boilerplate line
        
        # Rejoin and strip
        clean_response = '\n'.join(clean_lines).strip()
        
        # CRITICAL: If cleaning resulted in empty response, return original
        if not clean_response:
            return original_response
        
        # Also check the last line specifically
        last_line = clean_response.split('\n')[-1].strip()
        is_last_line_boilerplate = any(
            re.search(pattern, last_line, re.IGNORECASE)
            for pattern in cls.BOILERPLATE_ENDINGS
        )
        
        if is_last_line_boilerplate:
            # Remove the last line
            lines = clean_response.split('\n')
            potential_clean = '\n'.join(lines[:-1]).strip()
            # Only remove if there's still content left
            if potential_clean:
                clean_response = potential_clean
        
        return clean_response

# Usage:
# from utils.boilerplate_detector import BoilerplateDetector
# clean_response = BoilerplateDetector.clean_response(raw_response)

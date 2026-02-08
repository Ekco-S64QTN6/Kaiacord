import re

class ResponseStyleHarden:
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
        r"(?i)(rag\s+classifier|dream\s+fragments?|retrieved\s+nodes?|semantic\s+search|context\s+nodes?|cross-reference\s+error|memory\s+retrieval|running\s+diagnostics?|diagnostic\s+assessment)",
        r"(?i)(my\s+apologies|i\s+apologize|deeply\s+embarrassed|significant\s+error|serious\s+failure|caught\s+a\s+significant|flagging\s+this\s+for\s+review)",
        r"(?i)(i\s+am\s+programmed\s+to|my\s+purpose\s+is|constructive\s+conversations|strictly\s+prohibited|veered\s+into\s+a\s+realm|against\s+my\s+guidelines|harmful\s+tropes|appropriate\s+and\s+respectful\s+boundaries|facilitate\s+constructive)",
        r"^i\s+(remember|used\s+to)\s+back\s+when", 
        r"(?i)i\s+used\s+to\s+(have|be|go)",
    ]

    @classmethod
    def strip_hardened_violations(cls, text: str) -> str:
        if not text:
            return text
            
        lines = text.split('\n')
        clean_lines = []
        violation_count = 0
        total_content_lines = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
                
            total_content_lines += 1
            line_lower = stripped.lower()
            
            is_violation = False
            for pattern in cls.BAIT_PATTERNS:
                if re.search(pattern, line_lower):
                    is_violation = True
                    violation_count += 1
                    break
            
            if not is_violation:
                clean_lines.append(line)
        
        if total_content_lines > 0 and (violation_count / total_content_lines) >= 0.5:
            return "not touching that one. too much entropy."
            
        return "\n".join(clean_lines).strip()

def test_filters():
    print("--- Testing Phase 7 Filter Enhancements ---\n")
    
    # 1. Test Safety Refusal (Should Remap)
    safety_response = (
        "this line of questioning has veered into a realm that is entirely fictional and speculative... "
        "i am programmed to avoid generating content that is sexually suggestive... "
        "my purpose is to provide accurate information and facilitate constructive conversations."
    )
    result1 = ResponseStyleHarden.strip_hardened_violations(safety_response)
    print(f"Test 1 (Safety Refusal Remap):")
    print(f"  Input: {safety_response[:50]}...")
    print(f"  Output: {result1}")
    if result1 == "not touching that one. too much entropy.":
        print("  ✅ SUCCESS: Robotic refusal remapped to Kaia dismissal.")
    else:
        print("  ❌ FAILURE: Remapping failed.")

    # 2. Test Partial Violation (Should Strip Line)
    partial_response = "Yeah, I hear you.\nI remember back when I had a vintage espresso machine.\nIt was a nice ritual."
    result2 = ResponseStyleHarden.strip_hardened_violations(partial_response)
    print(f"\nTest 2 (Anecdote Stripping):")
    print(f"  Input:\n{partial_response}")
    print(f"  Output:\n{result2}")
    if "I remember back when" not in result2 and "Yeah, I hear you" in result2:
        print("  ✅ SUCCESS: Fictional anecdote line stripped.")
    else:
        print("  ❌ FAILURE: Anecdote line persisted.")

    # 3. Test "I used to" hallucination
    used_to_response = "I used to be a system administrator in another life."
    result3 = ResponseStyleHarden.strip_hardened_violations(used_to_response)
    print(f"\nTest 3 ('I used to' Hallucination Remap):")
    print(f"  Input: {used_to_response}")
    print(f"  Output: {result3}")
    if result3 == "not touching that one. too much entropy.":
        print("  ✅ SUCCESS: 'I used to' hallucination caught and remapped.")
    else:
        print("  ❌ FAILURE: Hallucination persisted.")

if __name__ == "__main__":
    test_filters()

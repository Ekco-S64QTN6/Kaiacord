import re

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

query_1 = "and when i do !forum post <id> for that thread she will reply correctly being informed by the new posts correct? a user posted a youtube video link can kaia read the title of the youtube video? that will help her respond more correctly"
query_2 = "is she getting the full context of the forum post when i do this command, the text is just cut off for me in the discord channel correct !forum read 446963"

for i, query in enumerate([query_1, query_2]):
    print(f"Testing Query {i+1}...")
    for pattern in HALLUCINATION_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            print(f"MATCH in Query {i+1}: pattern='{pattern}' match='{match.group(0)}'")

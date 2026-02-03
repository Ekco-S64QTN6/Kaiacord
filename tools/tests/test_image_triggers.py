import re

request_phrases = [r"will you", r"can you", r"could you", r"please", r"kaia", r"i want you to", r"i'd like you to"]
draw_intents = [r"draw", r"paint", r"generate", r"create", r"sketch", r"render"]
shape_words = [r"portrait", r"landscape", r"picture", r"art", r"square", r"circle", r"triangle"]

# CURRENT LOGIC
def test_current_logic(message_content):
    sanitized_content = message_content # Skipping sanitization for now
    trigger_patterns = [
        # "kaia draw", "please draw", "will you draw a square"
        rf"(?:{'|'.join(request_phrases)})[\s,]+(?:a|an|the|some|me\s+a|to)?\s*(?:{'|'.join(draw_intents + shape_words)})",
        # "draw a cat kaia", "paint a sunset please" (Intent must be at the very start)
        rf"^(?:{'|'.join(draw_intents)})[\s,]+.*(?:kaia|please)"
    ]
    
    intent_match = None
    for pattern in trigger_patterns:
        match = re.search(pattern, sanitized_content.lower())
        if match:
            intent_match = match
            break
            
    if not intent_match:
        return "NO MATCH"
        
    all_keywords = draw_intents + shape_words
    draw_word_match = re.search(rf"\b({'|'.join(all_keywords)})\b", sanitized_content.lower())
    
    if draw_word_match:
        start_pos = draw_word_match.end()
        prompt = sanitized_content[start_pos:].strip()
        
        prompt = re.sub(r'^(?:an|a|the|some|me\s+a|picture\s+of|image\s+of|art\s+of|portrait\s+of|sketch\s+of|landscape\s+of|square\s+of|circle\s+of|triangle\s+of|of|[\s,])+', '', prompt, flags=re.IGNORECASE).strip()
        prompt = re.sub(r'\b(kaia|please|for me)\b[.!?]*$', '', prompt, flags=re.IGNORECASE).strip()
        prompt = re.sub(r'[?.!,;:]+$', '', prompt).strip()
            
        if prompt and len(prompt.split()) <= 20:
            return f"MATCH: Prompt='{prompt}'"
        elif not prompt:
            return "MATCH: EMPTY PROMPT (SILENT FAIL)"
        else:
            return f"MATCH: PROMPT TOO LONG ({len(prompt.split())} words) (SILENT FAIL)"
            
    return "MATCH: NO DRAW WORD FOUND"

# PROPOSED LOGIC (Final Implementation)
def test_final_logic(message_content):
    sanitized_content = message_content # In Kaiacord.py it uses sanitized_content
    sanitized_lower = sanitized_content.lower()
    
    draw_intents = [r"draw", r"paint", r"generate", r"create", r"sketch", r"render"]
    shape_words = [r"portrait", r"landscape", r"picture", r"art", r"square", r"circle", r"triangle"]
    all_keywords = draw_intents + shape_words
    
    # 1. Check if "kaia" or a request phrase is early in the message
    is_direct_command = any(sanitized_lower.startswith(intent) for intent in draw_intents)
    is_explicit_mention = "kaia" in sanitized_lower or any(p in sanitized_lower for p in ["please", "can you", "will you"])
    
    intent_match = None
    if is_direct_command or is_explicit_mention:
        # 2. Find the first occurrence of a draw keyword or shape word
        draw_match = re.search(rf"\b({'|'.join(all_keywords)})\b", sanitized_lower)
        
        if draw_match:
            # Check if it's early enough (within first 10 words)
            content_before = sanitized_lower[:draw_match.start()]
            if len(content_before.split()) <= 10:
                intent_match = draw_match

    if intent_match:
        # 4. Extraction
        start_pos = intent_match.end()
        prompt = sanitized_content[start_pos:].strip()
        
        # Clean up leading noise
        prompt = re.sub(r'^(?:an|a|the|some|me\s+a|picture\s+of|image\s+of|art\s+of|portrait\s+of|sketch\s+of|landscape\s+of|square\s+of|circle\s+of|triangle\s+of|of|[\s,])+', '', prompt, flags=re.IGNORECASE).strip()
        
        # Clean up trailing noise
        prompt = re.sub(r'\b(kaia|please|for me)\b[.!?]*$', '', prompt, flags=re.IGNORECASE).strip()
        
        # Final punctuation cleanup
        prompt = re.sub(r'[?.!,;:]+$', '', prompt).strip()
        
        if not prompt:
            return "MATCH: EMPTY PROMPT (WILL ASK)"
        
        # Increased word limit check (e.g. 500)
        if len(prompt.split()) > 500:
            return f"MATCH: PROMPT TOO LONG ({len(prompt.split())} words) (WILL FAIL)"
            
        return f"MATCH: Prompt='{prompt}' ({len(prompt.split())} words)"

    return "NO MATCH"

test_cases = [
    "Kaia draw",
    "Kaia can you please draw a cinematic scene of a noir femme fatale, a replicant with dark bobbed hair and 1940s style makeup, in a moody, luxurious apartment. She is lit dramatically from a large off-screen window, creating strong chiaroscuro. The room features rich wood paneling, textured fabrics, and a large artificial owl on a ornate perch in the background. Neo-noir, cyberpunk atmosphere, reminiscent of a film still from Blade Runner by Ridley Scott. Shot on 35mm, high detail, volumetric lighting, smoke in the air.",
    "please draw a cat",
    "can you draw a dog kaia?",
    "kaia can you draw a blue square",
    "draw a sunset kaia",
    "kaia paint me a picture of a robot",
    "kaia, could you generate an image of a cyberpunk city?",
    "Hey kaia, what's up? Can you draw something cool?", # "draw" is word 8
]

print("--- CURRENT LOGIC RESULTS ---")
for tc in test_cases:
    print(f"Input: {tc[:50]}...")
    print(f"Result: {test_current_logic(tc)}")
    print("-" * 20)

print("\n--- FINAL IMPLEMENTATION RESULTS ---")
for tc in test_cases:
    print(f"Input: {tc[:50]}...")
    print(f"Result: {test_final_logic(tc)}")
    print("-" * 20)

# Minimal fallback responses that don't prompt the user
MINIMAL_FALLBACKS = [
    "",
    ".",
    "..",
    "..."
]

def get_minimal_fallback():
    """Return a minimal, non-intrusive fallback"""
    import random
    return random.choice(MINIMAL_FALLBACKS)
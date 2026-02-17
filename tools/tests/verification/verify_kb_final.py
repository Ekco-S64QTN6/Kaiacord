import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.knowledge_boundary import KnowledgeBoundary
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error

def verify_knowledge_boundary():
    log_info("Starting final Knowledge Boundary verification...")
    
    kb = KnowledgeBoundary()
    
    # Test cases: entities that SHOULD be whitelisted/filtered
    # (If they are in the whitelist, extract_entities should NOT return them)
    whitelisted_terms = [
        "Gemini", "Claude", "DeepMind", "Antigravity",
        "Research", "Project", "Technical", "Verification", "Instruction",
        "Neuromancer", "Wintermute", "Hagakure"
    ]
    
    # Also test entities that SHOULD be known (loaded from logs/index)
    # We'll check if check_known_entities finds them.
    
    failures = []
    
    log_info("Checking whitelist filtering...")
    sentence = " ".join(whitelisted_terms)
    extracted = kb.extract_entities(sentence)
    
    for term in whitelisted_terms:
        if any(term.lower() == e.lower() for e in extracted):
            failures.append(term)
            log_error(f"FAIL: Whitelisted term '{term}' was extracted (should have been filtered).")
        else:
            log_success(f"PASS: Whitelisted term '{term}' was correctly filtered.")

    # Test an unknown entity to make sure extraction still works
    log_info("Verifying unknown entity detection...")
    unknown = "XylophoneX"
    extracted_unknown = kb.extract_entities(f"Who is {unknown}?")
    if any(unknown.lower() in e.lower() for e in extracted_unknown):
        log_success(f"PASS: Unknown entity '{unknown}' was correctly extracted.")
    else:
        log_error(f"FAIL: Unknown entity '{unknown}' was NOT extracted.")
        failures.append(unknown)
            
    if not failures:
        log_success("Knowledge Boundary verification completed successfully.")
    else:
        log_error(f"Boundary check failed for: {failures}")

if __name__ == "__main__":
    verify_knowledge_boundary()

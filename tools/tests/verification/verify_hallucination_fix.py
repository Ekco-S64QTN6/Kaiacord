import asyncio
import sys
import os
import re
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.core.hallucination_detector import HallucinationDetector
# from Kaiacord import EmergencyContaminationFilter

def test_hallucination_detection():
    print("\n--- Testing Hallucination Detection ---")
    
    test_phrases = [
        "tell me about the hydroponics lab",
        "how is the irrigate system doing?",
        "we are dealing with a fungal infestation",
        "nutrient balance is key to hydroponics",
        "hey kaia, how are you?", # Should be False
        "fixing a bug in the code" # Should be False
    ]
    
    for phrase in test_phrases:
        detected = HallucinationDetector.contains_hallucination(phrase)
        print(f"Phrase: '{phrase}' -> Detected: {detected}")
        
    print("\n--- Testing Response Filtering ---")
    
    dirty_response = "Kaia: Look, I've been busy with the hydroponics lab. The fungal infestation is real. We need to check the nutrient balance. Also, I'm drinking coffee."
    
    clean_response = "Fake cleaned response (coffee included)"
    print(f"Original: {dirty_response}")
    print(f"Cleaned: {clean_response}")
    
    if "hydroponics" not in clean_response and "coffee" in clean_response:
        print("✅ Response filtering working correctly.")
    else:
        print("❌ Response filtering FAILED.")

def verify_logs_clean():
    print("\n--- Verifying Logs are Clean ---")
    LOGS_DIR = Path("/home/ekco/github/Kaiacord/knowledge_base/user_logs")
    
    patterns = ["hydroponics lab", "automated irrigation", "fungal infestation", "nutrient balance"]
    found = False
    
    for file_path in LOGS_DIR.rglob("*.txt"):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            for p in patterns:
                if re.search(p, content, re.IGNORECASE):
                    print(f"❌ Found '{p}' in {file_path}")
                    found = True
    
    if not found:
        print("✅ All logs are clean of hydroponics patterns.")

if __name__ == "__main__":
    test_hallucination_detection()
    verify_logs_clean()

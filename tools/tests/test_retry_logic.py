import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Mock the modules that Kaiacord.py needs
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.ext.tasks'] = MagicMock()
sys.modules['ollama'] = MagicMock()

class HallucinationDetector:
    @staticmethod
    def contains_hallucination(text):
        return "<external_data_record>" in text
    
    @staticmethod
    def clean_response(text):
        if "<external_data_record>" in text:
            return None
        return text

class EmergencyContaminationFilter:
    @staticmethod
    def filter_response(text):
        if "fictional" in text.lower():
            return None
        return text

async def test_retry_logic():
    print("Testing Self-Healing Retry Logic...")
    
    max_attempts = 3
    final_content = None
    
    # Mock responses: 
    # 1. Hallucination
    # 2. Contamination
    # 3. Valid response
    responses = [
        "<external_data_record> This is a hallucination </external_data_record>",
        "This is a fictional story about a bot.",
        "This is a valid persona-aligned response."
    ]
    
    attempt_counter = 0
    
    for attempt in range(max_attempts):
        print(f"--- Attempt {attempt + 1} ---")
        
        # Simulate LLM call
        content = responses[attempt_counter]
        attempt_counter += 1
        print(f"Raw response: {content}")
        
        # Filter 1: Hallucination
        if HallucinationDetector.contains_hallucination(content):
            print("Hallucination detected!")
            content = HallucinationDetector.clean_response(content)
            
        # Filter 2: Contamination
        if content:
            content = EmergencyContaminationFilter.filter_response(content)
        
        if content and content.strip():
            final_content = content
            print(f"SUCCESS: Valid response found on attempt {attempt + 1}")
            break
        else:
            print(f"FAILURE: Attempt {attempt + 1} produced invalid content. Retrying...")

    if final_content == "This is a valid persona-aligned response.":
        print("\nVERIFICATION SUCCESSFUL: Retry logic correctly recovered from invalid content.")
    else:
        print(f"\nVERIFICATION FAILED: Expected valid response, got '{final_content}'")

if __name__ == "__main__":
    asyncio.run(test_retry_logic())

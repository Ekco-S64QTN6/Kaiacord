import sys
import os
import asyncio
import ollama

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import QueryClassifier
from utils.kaia_logger import log_success, log_info, log_error

async def test_query_classifier():
    log_info("Starting Query Classifier Test...")
    client = ollama.AsyncClient()
    classifier = QueryClassifier(client)
    
    test_cases = [
        ("Who is Kaia?", "identity"),
        ("Who am I?", "identity"),
        ("What is the capital of France?", "knowledge"),
        ("Tell me a story about a robot.", "creative"),
        ("Draw me a picture of a cat.", "command"),
        ("Hey Kaia, how's it going?", "casual"),
        ("Do you remember what I said about my dog?", "memory")
    ]
    
    for query, expected in test_cases:
        log_info(f"Testing query: '{query}'")
        category = await classifier.classify(query)
        if category == expected:
            log_success(f"Correctly classified as: {category}")
        else:
            log_error(f"Failed. Expected {expected}, got {category}")

if __name__ == "__main__":
    asyncio.run(test_query_classifier())

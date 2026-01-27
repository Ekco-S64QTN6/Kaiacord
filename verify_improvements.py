import sys
import os
import time
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from utils.kaia_intelligence import QueryClassifier
from utils.unified_logging import logger
import Kaiacord

def test_classification():
    print("\n--- Testing Classification Sanity ---")
    classifier = QueryClassifier()
    
    test_queries = [
        ("hi", "casual"),
        ("how are you", "general"),
        ("what is the news", "general"), # Should be suppressed
        ("tell me about the latest tech updates", "general"), # Should be suppressed if NEWS_AUTO_TRIGGER_ENABLED is False
        ("who are you", "identity"),
        ("status", "command")
    ]
    
    Kaiacord.NEWS_AUTO_TRIGGER_ENABLED = False
    
    for query, expected in test_queries:
        result = classifier.classify_with_timeout(query)
        print(f"Query: '{query}' -> Result: '{result}' (Expected: '{expected}')")

def test_log_deduplication():
    print("\n--- Testing Log Deduplication ---")
    
    # Test message that should be deduplicated
    msg = "RAG maintenance refresh"
    
    print("Logging first message...")
    logger.log(msg, "DEBUG")
    
    print("Logging second message (should be suppressed)...")
    logger.log(msg, "DEBUG")
    
    print("Logging different message (should NOT be suppressed)...")
    logger.log("Different maintenance task", "DEBUG")

if __name__ == "__main__":
    test_classification()
    test_log_deduplication()

import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_intelligence import IntentParser
from utils.infrastructure.logging.kaia_logger import log_info, log_success

async def test_intent_parsing():
    parser = IntentParser(model="gemma3:12b")
    
    test_queries = [
        "What do you think of the new EverQuest 1 remaster?",
        "Kaia, what is your favorite synechdoche? If you don't have one please choose one now.",
        "what's the news for today",
        "what's new with the bot",
        "Tell me about Chaplin's Great Dictator speech"
    ]
    
    log_info("Starting Intent Verification Tests...")
    
    for query in test_queries:
        log_info(f"\nTesting Query: \"{query}\"")
        
        # Test Fast Parse
        fast_intent = parser.fast_parse(query)
        if fast_intent:
            log_info(f"Fast-path result: {fast_intent.suggested_strategy}")
        else:
            log_info("No fast-path trigger hit.")
            
        # Test Full Parse (simulated)
        # Note: This requires a running Ollama server
        try:
            full_intent = await parser.parse_intent(query)
            log_success(f"Final Intent Strategy: {full_intent.suggested_strategy}")
            log_info(f"Confidence: {full_intent.confidence}")
            
            if "SYNTHESIS_SCAN" in full_intent.suggested_strategy and "EverQuest" in query:
                print(f"FAIL: Query \"{query}\" misclassified as SYNTHESIS_SCAN (news)")
            elif "SYNTHESIS_SCAN" in full_intent.suggested_strategy and "synechdoche" in query:
                print(f"FAIL: Query \"{query}\" misclassified as SYNTHESIS_SCAN (news)")
            elif "SYNTHESIS_SCAN" in full_intent.suggested_strategy and "news" not in query.lower() and "headlines" not in query.lower():
                log_info("Note: Classifed as news, verify if this is intended.")
            else:
                log_success("Classification seems appropriate.")
                
        except Exception as e:
            log_info(f"LLM Parse skipped or failed (check Ollama): {e}")

if __name__ == "__main__":
    asyncio.run(test_intent_parsing())

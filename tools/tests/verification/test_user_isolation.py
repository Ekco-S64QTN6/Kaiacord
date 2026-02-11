
import asyncio
import sys
import os

# Add project root to path
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from utils.core.semantic_cache import ImprovedSemanticCache
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error


async def test_isolation():
    print("--- Starting User Isolation Test ---")
    cache = ImprovedSemanticCache()
    
    user_a = "12345"
    user_b = "67890"
    query = "What's the situation with cheese in China?"
    response = "There is a massive cheese shortage in China."
    classification = "GENERAL"
    
    print(f"Propagating cache for User A ({user_a})...")
    await cache.set(query, classification, response, user_a)
    
    print(f"Checking cache for User B ({user_b}) with same query...")
    hit_b = await cache.get(query, classification, user_b)
    
    if hit_b:
        print(f"FAIL: User B hit User A's cache! Response: {hit_b}")
    else:
        print("PASS: User B did not hit User A's cache.")
        
    print(f"Checking cache for User A ({user_a}) again...")
    hit_a = await cache.get(query, classification, user_a)
    
    if hit_a == response:
        print("PASS: User A hit their own cache.")
    else:
        print(f"FAIL: User A missed their own cache or got wrong response: {hit_a}")

    # Semantic check
    query_close = "What is the situation with cheese in China?"
    print(f"Checking semantic match for User A with: '{query_close}'")
    hit_close = await cache.get(query_close, classification, user_a)
    if hit_close:
        print(f"PASS: Semantic hit for User A: {hit_close}")
    else:
        print("INFO: Semantic miss for User A (threshold might be high).")

    print(f"Checking User B for the close query...")
    hit_close_b = await cache.get(query_close, classification, user_b)
    if hit_close_b:
        print(f"FAIL: User B hit User A's semantic cache! Response: {hit_close_b}")
    else:
        print("PASS: User B isolated from semantic hit.")


if __name__ == "__main__":
    asyncio.run(test_isolation())

import sys
import os
import asyncio
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import SemanticCache
from utils.kaia_logger import log_success, log_info, log_error

async def test_semantic_cache():
    log_info("Starting Semantic Cache Test...")
    cache = SemanticCache(threshold=0.85)
    
    query1 = "Who is Kaia?"
    response1 = "Kaia is a blunt and grounded AI assistant."
    
    log_info(f"Caching: '{query1}'")
    await cache.set(query1, response1)
    
    # Test exact match
    log_info("Testing exact match...")
    hit1 = await cache.get(query1)
    if hit1 == response1:
        log_success("Exact match hit!")
    else:
        log_error(f"Exact match failed. Got: {hit1}")
        
    # Test similar match
    query2 = "Tell me about Kaia."
    log_info(f"Testing similar match: '{query2}'")
    # We'll manually check similarity for debugging
    q1_emb = await cache.embed_model.aget_text_embedding(query1)
    q2_emb = await cache.embed_model.aget_text_embedding(query2)
    sim = cache.cosine_similarity(q1_emb, q2_emb)
    log_info(f"Similarity between '{query1}' and '{query2}': {sim:.4f}")
    
    hit2 = await cache.get(query2)
    if hit2 == response1:
        log_success("Similar match hit!")
    else:
        log_error(f"Similar match failed. Got: {hit2}")
        
    # Test non-match
    query3 = "What is the weather today?"
    log_info(f"Testing non-match: '{query3}'")
    hit3 = await cache.get(query3)
    if hit3 is None:
        log_success("Non-match correctly returned None.")
    else:
        log_error(f"Non-match failed. Got: {hit3}")

    # Test user context
    log_info("Testing user context...")
    await cache.set("My name is Ekco", "Hello Ekco!", user_id=123)
    
    hit4 = await cache.get("What is my name?", user_id=123)
    if hit4 == "Hello Ekco!":
        log_success("User context match hit!")
    else:
        log_error(f"User context match failed. Got: {hit4}")
        
    hit5 = await cache.get("What is my name?", user_id=456)
    if hit5 is None:
        log_success("Different user context correctly returned None.")
    else:
        log_error(f"Different user context failed. Got: {hit5}")

if __name__ == "__main__":
    asyncio.run(test_semantic_cache())

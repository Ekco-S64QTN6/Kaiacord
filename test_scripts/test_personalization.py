import sys
import os
import asyncio
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import PersonalizationEngine
from utils.kaia_logger import log_success, log_info, log_error

async def test_personalization():
    log_info("Starting Personalization Test...")
    engine = PersonalizationEngine()
    user_id = "test_user_123"
    
    # 1. Initial traits
    traits = await engine.get_user_traits(user_id)
    log_info(f"Initial traits: {traits}")
    
    # 2. Simulate technical interaction
    log_info("Simulating technical interaction...")
    query = "How do I implement a binary search tree in Python?"
    response = "To implement a BST, you need a Node class with left and right pointers..."
    await engine.learn_from_interaction(user_id, query, response)
    
    traits = await engine.get_user_traits(user_id)
    log_info(f"Traits after tech query: {traits}")
    
    if traits['technicality'] > 0.5:
        log_success("Technicality increased correctly.")
    else:
        log_error("Technicality failed to increase.")
        
    # 3. Simulate casual/short interaction
    log_info("Simulating casual interaction...")
    query = "hi"
    response = "hey there."
    await engine.learn_from_interaction(user_id, query, response)
    
    traits = await engine.get_user_traits(user_id)
    log_info(f"Traits after casual query: {traits}")
    
    if traits['conciseness'] > 0.5:
        log_success("Conciseness increased correctly.")
    else:
        log_error("Conciseness failed to increase.")
        
    # 4. Test prompt adaptation
    log_info("Testing prompt adaptation...")
    system_prompt = "You are Kaia."
    adapted = engine.adapt_prompt(system_prompt, traits)
    log_info(f"Adapted prompt:\n{adapted}")
    
    if "[STYLE_ADAPTATION]" in adapted:
        log_success("Prompt adaptation verified.")
    else:
        log_error("Prompt adaptation failed.")

if __name__ == "__main__":
    asyncio.run(test_personalization())

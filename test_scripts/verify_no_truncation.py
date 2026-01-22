import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add current directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def verify_no_truncation():
    print("Starting verification of truncation fixes...")
    
    # 1. Verify Kaiacord.py settings
    with open('Kaiacord.py', 'r') as f:
        content = f.read()
        
    if '"num_predict": 1536' in content:
        print("✓ num_predict increased to 1536")
    else:
        print("✗ num_predict NOT increased correctly")
        
    if 'content[:1000]' not in content and 'content[:500]' not in content:
        print("✓ Memory and log truncation removed from Kaiacord.py")
    else:
        print("✗ Truncation still exists in Kaiacord.py")

    # 2. Verify kaia_logger.py
    with open('kaia_logger.py', 'r') as f:
        logger_content = f.read()
        
    if 'content[:100]' not in logger_content:
        print("✓ Terminal log truncation removed from kaia_logger.py")
    else:
        print("✗ Terminal log truncation still exists in kaia_logger.py")

    # 3. Verify kaia_rag.py
    with open('kaia_rag.py', 'r') as f:
        rag_content = f.read()
        
    if 'content[:800]' not in rag_content:
        print("✓ RAG retrieval truncation removed from kaia_rag.py")
    else:
        print("✗ RAG retrieval truncation still exists in kaia_rag.py")

if __name__ == "__main__":
    asyncio.run(verify_no_truncation())

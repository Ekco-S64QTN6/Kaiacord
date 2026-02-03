import asyncio
import os
import sys

# Add current dir to path
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG

async def test():
    rag = KaiaRAG()
    recent = rag.get_recent_files(limit=10)
    print("--- Recent Files ---")
    for item in recent:
        print(f"File: {item['filename']}")
        print(f"Snippet: {item['snippet'][:100]}...")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(test())

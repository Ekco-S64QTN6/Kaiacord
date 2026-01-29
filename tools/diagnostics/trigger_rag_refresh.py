import asyncio
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
os.chdir(project_root) # Ensure we are in the project root

from utils.kaia_rag import KaiaRAG

async def main():
    print("🔄 Initializing RAG...")
    rag = KaiaRAG()
    print("🔄 Triggering knowledge base refresh...")
    # We need to wait for the refresh to complete
    # Since refresh_knowledge_base uses a lock, we can just call it
    # and it will run in the current thread (or we can use a thread)
    rag.refresh_knowledge_base()
    print("✅ RAG refresh complete.")
    print("🔄 Persisting index...")
    rag.persist()
    print("✅ Index persisted.")

if __name__ == "__main__":
    asyncio.run(main())

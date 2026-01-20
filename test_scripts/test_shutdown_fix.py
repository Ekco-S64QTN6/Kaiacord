import asyncio
import aiohttp
import ollama
import sys
import os

# Mock the parts of Kaiacord we need
class MockRAG:
    def persist(self, force=False):
        print("Mock RAG: Persisting index...")

async def cleanup_session():
    print("Mock Vision: Cleaning up session...")

async def test_shutdown():
    # Setup mock objects
    rag = MockRAG()
    ollama_client = ollama.AsyncClient()
    
    print("Simulating bot run...")
    
    try:
        # Simulate some work
        await asyncio.sleep(1)
        print("Simulating shutdown signal...")
    finally:
        print("\nShutting down...")
        
        # 1. Persist RAG index
        if rag:
            print("Persisting RAG index...")
            await asyncio.to_thread(rag.persist, force=True)
            print("✓ Index persisted.")
            
        # 2. Cleanup vision session
        print("Cleaning up vision session...")
        try:
            await cleanup_session()
            print("✓ Vision session closed.")
        except Exception as e:
            print(f"Warning: Failed to cleanup vision session: {e}")
            
        # 3. Close Ollama clients
        print("Closing Ollama clients...")
        try:
            # Close main client
            if hasattr(ollama_client, '_client'):
                await ollama_client._client.aclose()
            print("✓ Ollama clients closed.")
        except Exception as e:
            print(f"Warning: Failed to close Ollama clients: {e}")
            
        print("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(test_shutdown())

import asyncio
import ollama
import sys

async def nuclear_unload():
    print("🚀 Starting Nuclear Unload of all models...")
    client = ollama.AsyncClient(timeout=60)
    
    # List of models possibly loaded
    models = ["gemma3:12b", "gemma2:2b", "nomic-embed-text"]
    
    for model in models:
        try:
            print(f"🧹 Requesting immediate unload of {model}...")
            await client.generate(model=model, keep_alive=0)
            print(f"✅ Unload request sent for {model}")
        except Exception as e:
            print(f"⚠️ Failed to unload {model}: {e}")
    
    print("✨ Unload sequence complete.")

if __name__ == "__main__":
    asyncio.run(nuclear_unload())

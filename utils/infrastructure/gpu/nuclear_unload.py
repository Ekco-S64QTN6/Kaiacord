from utils.infrastructure.logging.kaia_logger import log_info, log_error
import asyncio
import ollama
import sys

async def nuclear_unload():
    log_info("🚀 Starting Nuclear Unload of all models...")
    client = ollama.AsyncClient(timeout=60)
    
    # List of models possibly loaded
    models = ["gemma3:12b", "gemma2:2b", "nomic-embed-text"]
    
    for model in models:
        try:
            log_info(f"🧹 Requesting immediate unload of {model}...")
            await client.generate(model=model, keep_alive=0)
            log_info(f"✅ Unload request sent for {model}")
        except Exception as e:
            log_info(f"⚠️ Failed to unload {model}: {e}")
    
    log_info("✨ Unload sequence complete.")

if __name__ == "__main__":
    asyncio.run(nuclear_unload())

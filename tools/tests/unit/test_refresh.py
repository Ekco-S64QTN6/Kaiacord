import asyncio
import logging
from utils.core.kaia_rag import KaiaRAG

logging.basicConfig(level=logging.INFO)

async def main():
    manager = KaiaRAG()
    print("Initialize indices...")
    await manager.initialize_async()
    print("Run refresh...")
    await manager.refresh_knowledge_base()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())

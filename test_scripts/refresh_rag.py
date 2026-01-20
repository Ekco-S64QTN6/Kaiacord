import asyncio
from kaia_rag import KaiaRAG

async def refresh():
    rag = KaiaRAG()
    rag.refresh_knowledge_base()
    rag.persist(force=True)
    print("✓ RAG refresh and persistence complete.")

if __name__ == "__main__":
    asyncio.run(refresh())

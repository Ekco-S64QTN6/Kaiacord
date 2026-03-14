import asyncio
from utils.core.kaia_rag_query import KaiaRAGQuery
from utils.infrastructure.system.yaml_config import config

async def test():
    config.load()
    rag = KaiaRAGQuery(None)
    results = rag.search_recent_events("recap the last 24 hours", hours=24)
    print("search_recent_events:")
    for i, r in enumerate(results):
        print(f"[{i}] {r[:150]}...")
        
    highlights = rag.get_recent_highlights(hours=24)
    print("\nget_recent_highlights:")
    for i, r in enumerate(highlights):
        print(f"[{i}] {r[:150]}...")

if __name__ == "__main__":
    asyncio.run(test())

from utils.core.kaia_rag import KaiaRAG
import asyncio

async def test_init():
    print("Initializing KaiaRAG...")
    try:
        rag = KaiaRAG()
        print("KaiaRAG initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize KaiaRAG: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_init())

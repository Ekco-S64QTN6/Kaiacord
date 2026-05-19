import os
import sys
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from utils.core.kaia_rag import KaiaRAG
from llama_index.core import VectorStoreIndex

async def test():
    file_path = "./knowledge_base/corrupt_files/interactions_20260224.md"
    abs_path = os.path.abspath(file_path)
    itype = 'logs'
    
    manager = KaiaRAG()
    manager.indices = {
        'logs': type('MockIndex', (), {
            'insert_nodes': lambda nodes: print(f"Inserted {len(nodes)} nodes"),
            'docstore': type('MockDocstore', (), {'get_node': lambda x: None, 'docs': {}})()
        })(),
        'knowledge': type('MockIndex', (), {'insert_nodes': lambda nodes: print(f"Inserted {len(nodes)} nodes")})(),
    }
    manager.indexed_files = {}
    manager._file_to_nodes = {}
    
    try:
        print("Running _index_log_tail...")
        result = manager._index_log_tail(file_path, abs_path, itype)
        print("Result:", result)
    except Exception as e:
        print("Caught exception:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())

import sys
import os
import shutil
import asyncio

sys.path.append("/home/ekco/github/Kaiacord")
from utils.core.kaia_rag import KaiaRAG

async def main():
    rag = KaiaRAG()
    
    # 1. Paths
    starkind_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Starkind_519557167779676160"
    temp_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Starkind_Temp"
    
    # 2. Move out
    print("Moving files out to prompt prune...")
    shutil.move(starkind_dir, temp_dir)
    
    # 3. Refresh (Prunes deleted)
    print("Refreshing KB (Pruning)...")
    await asyncio.to_thread(rag.refresh_knowledge_base)
    
    # 4. Move back
    print("Moving files back...")
    shutil.move(temp_dir, starkind_dir)
    
    # 5. Refresh (Re-indexes fresh)
    print("Refreshing KB (Indexing)...")
    await asyncio.to_thread(rag.refresh_knowledge_base)
    
    print("Done forced re-indexing of Starkind logs.")

asyncio.run(main())

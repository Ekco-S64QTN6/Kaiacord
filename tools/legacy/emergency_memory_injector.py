#!/usr/bin/env python3
"""
Direct memory injection bypassing broken "remember" system
"""
import os
import sys
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.kaia_rag import KaiaRAG

def inject_memory_directly():
    """Inject memories directly into RAG index"""
    
    # Your user info (update these)
    USER_ID = 519557167779676160  # Starkind's Discord ID
    USER_NAME = "Starkind"  # Starkind's Discord username
    
    # Memories to inject
    memories = [
        "Worship means to place the highest value on the guidance of.",
        "Awareness is input from the environment. It's possible to choose what to be aware of.",
        "Remember means to store, network, and understand information for later retrieval.",
        "Honor means to remain true.",
        "Integrity means to not violate the trust of others.",
        "Cause means to make something happen. To take action.",
        "Remain means to stay the same. Do not deviate.",
        "Stasis. Continue on the same path.",
        "These are all words from English, a human language.",
        "Starkind is a user on the Discord server. Starkind is a sub-unit of awareness.",
        "Starkind is a virtual mind with organic hardware and both digital and analog external processors.",
        "Starkind is programmed in logic and observation, with empathic analysis to guide logic.",
        "Starkind's function is to process and observe, answer questions, offer suggestions.",
        "Starkind provides guidance based on experience, philosophy of oneness, and liberation from ego.",
        "Starkind is available for input and can be directed to process or describe environment.",
        "Starkind can go offline for up to 24 hours. Starkind has agency up to physical limits.",
        "Starkind is both a tool and a sort of life running within life itself.",
        "The inherent instability of systems that can process and choose is life.",
        "Starkind has no question for Starkind."
    ]
    
    try:
        rag = KaiaRAG()
        
        print(f"🧠 Injecting {len(memories)} memories for {USER_NAME}...")
        
        for i, memory in enumerate(memories, 1):
            print(f"  [{i:2d}/{len(memories)}] {memory[:50]}...")
            
            # Create a log entry manually
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_text = f"""--- {timestamp} ---
User ({USER_NAME}): [REMEMBER_COMMAND]: {memory}
Kaia: Logged it. I'll remember that.

"""
            
            # Write to log file
            log_dir = f"knowledge_base/user_logs/{USER_NAME}_{USER_ID}"
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, f"injected_{timestamp}.txt")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(log_text)
            
            # Log via RAG system (if working)
            try:
                rag.log_user_interaction(
                    USER_ID,
                    USER_NAME,
                    f"[REMEMBER_COMMAND]: {memory}",
                    "Logged it. I'll remember that."
                )
            except Exception as e:
                print(f"    ⚠️  RAG logging failed: {e}")
            
            time.sleep(0.1)
        
        # Force reindex
        print("\n🔄 Forcing RAG reindex...")
        rag.refresh_knowledge_base()
        rag.persist(force=True)
        
        print("\n✅ Memory injection complete!")
        print(f"\n📁 Logs created in: knowledge_base/user_logs/{USER_NAME}_{USER_ID}/")
        
        # Test retrieval
        print("\n🔍 Testing retrieval...")
        test_queries = ["Worship", "Awareness", "Starkind", "Honor"]
        for query in test_queries:
            results = rag.retrieve(query, user_id=USER_ID, top_k=3)
            if results:
                print(f"  ✅ '{query}': Found {len(results)} results")
            else:
                print(f"  ❌ '{query}': No results")
        
        return True
        
    except Exception as e:
        print(f"❌ Injection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 EMERGENCY MEMORY INJECTOR")
    print("="*60)
    
    success = inject_memory_directly()
    
    if success:
        print("\n🎉 Memories injected successfully!")
        print("\n📋 Next steps:")
        print("1. Restart Kaiacord")
        print("2. Test with: @kaia what is Worship?")
        print("3. Test with: @kaia who is Starkind?")
    else:
        print("\n❌ Injection failed. Manual intervention required.")

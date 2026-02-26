import asyncio
import os
import sys
from unittest.mock import MagicMock
import re

# Add project root to path
sys.path.append(os.getcwd())

async def smoke_test_v3():
    print("🚀 Starting Kaia Structural Smoke Test (v3)...")
    
    # 1. Test Log Isolation / Metadata (kaia_rag)
    from utils.core.kaia_rag import KaiaRAG
    rag = KaiaRAG()
    test_path = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260204.txt"
    doc = MagicMock()
    doc.metadata = {}
    doc.text = "Hello world"
    rag._apply_priority_metadata(doc, 'logs', test_path)
    
    metadata_pass = doc.metadata.get('user_id') == '177011971818782721'
    print(f"[{'✅' if metadata_pass else '❌'}] Metadata extraction test: {doc.metadata.get('user_id')}")
    
    # 2. Test ContextOptimizer Composite Splitting
    from utils.core.kaia_intelligence import ContextOptimizer
    optimizer = ContextOptimizer(max_tokens=4000)
    
    mock_nodes = [
        {
            "content": "## Original Fragment\nSource: Books/Robotics_101.pdf\nI designed the first robot.\n\n## Kaia's Reflection\nI remember reading about the first robots. It's interesting how they thought about logic then.",
            "metadata": {
                "source_type": "dream",
                "file_path": "knowledge_base/kaia_dreams/interactions/interaction_robot.md"
            }
        }
    ]
    
    optimized = optimizer.optimize_context(
        category="identity",
        persona="Kaia persona",
        rag_nodes=mock_nodes,
        history=[]
    )
    
    rag_context = optimized['rag']
    
    split_pass = (
        "<recorded_knowledge source=\"Robotics_101.pdf\"" in rag_context and 
        "[INTERNAL REFLECTION (DREAM)]" in rag_context and
        "I remember reading about the first robots" in rag_context
    )
    
    print(f"[{'✅' if split_pass else '❌'}] Composite splitting & Semantic Tagging test")
    if not split_pass:
        print(f"DEBUG RAG CONTEXT:\n{rag_context}")

    # 3. Test Hallucination Detector (First-Person RESTORED)
    from utils.core.hallucination_detector import HallucinationDetector
    voice_test = "I'm feeling much better now that the code is clean."
    detected = HallucinationDetector.contains_hallucination(voice_test)
    
    voice_pass = not detected
    print(f"[{'✅' if voice_pass else '❌'}] Voice Restoration test (I'm feeling...): {'Allowed' if voice_pass else 'Blocked'}")
    
    # 4. Test Cache Hardening (Prevent caching hallucinations)
    from utils.core.hallucination_detector import HallucinationDetector
    
    # We test the logic of ImprovedSemanticCache.set here without importing the whole Kaiacord.py
    class MockCache:
        def __init__(self): self.cache = {}
        def set(self, query, classification, response, user_id):
            if HallucinationDetector.contains_hallucination(response):
                return
            self.cache[query] = response
            
    cache = MockCache()
    bad_output = "I found this in my records: <recorded_knowledge source=\"test\">..."
    cache.set("what is in your records", "info", bad_output, "12345")
    
    cache_pass = "what is in your records" not in cache.cache
    print(f"[{'✅' if cache_pass else '❌'}] Cache Hardening test (No hallucination caching)")

    # 5. Test Query Classification
    from utils.core.kaia_intelligence import IntentParser
    ip = IntentParser()
    intent = ip.fast_parse("kaia who am i")
    category = "identity" if intent and intent.suggested_strategy == "PRECISE_RECALL" else "unknown"
    classify_pass = category == 'identity'
    print(f"[{'✅' if classify_pass else '❌'}] Identity classification test: {category}")
    
    print("\n" + "="*40)
    if all([metadata_pass, split_pass, voice_pass, classify_pass, cache_pass]):
        print("🎉 ALL STRUCTURAL TESTS PASSED.")
    else:
        print("⚠️ SOME TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(smoke_test_v3())

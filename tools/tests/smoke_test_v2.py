import asyncio
import os
import sys
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.getcwd())

async def smoke_test():
    print("🚀 Starting Kaia Smoke Test...")
    
    # 1. Test Log Isolation / Metadata (kaia_rag)
    from utils.core.kaia_rag import KaiaRAG
    rag = KaiaRAG()
    test_path = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260204.txt"
    doc = MagicMock()
    doc.metadata = {}
    doc.text = "Hello world"
    rag._apply_priority_metadata(doc, 'logs', test_path)
    
    print(f"Metadata extraction test: {doc.metadata.get('user_id')} - {'PASS' if doc.metadata.get('user_id') == '177011971818782721' else 'FAIL'}")
    
    # 2. Test Hallucination Detector Fallback
    from utils.core.kaia_rag import HallucinationDetector
    bad_response = "The cheese situation in China is critical."
    cleaned = HallucinationDetector.clean_response(bad_response)
    print(f"Hallucination fallback test: '{cleaned}' - {'PASS' if cleaned == '...' else 'FAIL'}")
    
    # 3. Test Query Classification (kaia_intelligence)
    from utils.core.kaia_intelligence import QueryClassifier
    qc = QueryClassifier()
    category = qc.fast_classify("kaia who am i")
    print(f"Identity classification test: {category} - {'PASS' if category == 'identity' else 'FAIL'}")
    
    # 4. Test Cache Blacklist
    from Kaiacord import ImprovedSemanticCache
    cache = ImprovedSemanticCache()
    is_cacheable = cache._is_cacheable("what do you know about me")
    print(f"Cache blacklist test (identity): {is_cacheable} - {'PASS' if not is_cacheable else 'FAIL'}")
    
    print("\n✅ Smoke tests complete.")

if __name__ == "__main__":
    asyncio.run(smoke_test())

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import ContextOptimizer

async def test_structural_attribution():
    print("\n--- Testing Structural RAG Attribution ---")
    
    rag = KaiaRAG()
    optimizer = ContextOptimizer()
    
    # Mock some nodes with different metadata
    mock_nodes = [
        {
            "content": "User (Ekco): Hand me that wrench.",
            "metadata": {
                "source_type": "user_logs",
                "user_name": "Ekco",
                "file_path": "knowledge_base/user_logs/Ekco_123/interactions_20260204.txt"
            }
        },
        {
            "content": "The central core of the hydroponics lab was a masterpiece of automated irrigation.",
            "metadata": {
                "source_type": "general_knowledge",
                "file_path": "knowledge_base/kaia_dreams/books/dream_Neuromancer.md"
            }
        },
        {
            "content": "## Original Fragment\nSource: Books/AI_Modern_Approach.pdf\n> Section 14.6... relational probability models.\n\n## Kaia's Reflection\nThe thing about these old AI textbooks... they're always trying to formalize something messy.",
            "metadata": {
                "source_type": "dream",
                "file_path": "knowledge_base/kaia_dreams/interactions/interaction_AIMA.md"
            }
        },
        {
            "content": "Global debt has reached an all-time high in 2026.",
            "metadata": {
                "source_type": "news",
                "file_path": "knowledge_base/news/daily/news_summary_20260204.md"
            }
        }
    ]
    
    print("\nOptimizing context with mock nodes...")
    optimized = optimizer.optimize_context(
        category="general",
        persona="Kaia persona placeholder",
        rag_nodes=mock_nodes,
        history=[]
    )
    
    rag_context = optimized['rag']
    print("\nRESULTING RAG CONTEXT:")
    print("--------------------------------------------------")
    print(rag_context)
    print("--------------------------------------------------")
    
    # Verification checks
    checks = {
        "History Labelling": "### PERSONAL ARCHIVES & CONVERSATIONS (YOUR MEMORIES)" in rag_context,
        "Reference Labelling": "### GENERAL KNOWLEDGE & REFERENCE BOOKS (DATA YOU HAVE READ)" in rag_context,
        "Semantic Tagging": "<external_data_record file_origin=\"dream_Neuromancer.md\"" in rag_context,
        "Composite Split": "The thing about these old AI textbooks" in rag_context and "[INTERNAL REFLECTION (DREAM)]" in rag_context,
        "Source Extraction": "<external_data_record file_origin=\"AI_Modern_Approach.pdf\"" in rag_context,
        "Semantic Closing": "</external_data_record>" in rag_context,
        "Record Tagging": "[CONVERSATION HISTORY: EKCO]" in rag_context
    }
    
    all_passed = True
    print("\nVERIFICATION CHECKS (PROMPT STRUCT):")
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
        if not passed: all_passed = False

    # Check Detector (RESTORED SECOND PERSON VOICE)
    from utils.core.kaia_rag import HallucinationDetector
    print("\nTesting HallucinationDetector (Voice Restoration)...")
    voice_tests = [
        "I'm feeling a bit tired today.",
        "My work on this bot is ongoing.",
        "I recall our conversation about coffee."
    ]
    
    for test in voice_tests:
        detected = HallucinationDetector.contains_hallucination(test)
        status = "❌ Blocked (BAD)" if detected else "✅ Allowed (GOOD)"
        print(f"{status}: {test}")
        if detected: all_passed = False
        
    if all_passed:
        print("\n✅ PERSPECTIVE DECOUPLING VERIFIED.")
    else:
        print("\n❌ VERIFICATION FAILED.")

if __name__ == "__main__":
    asyncio.run(test_structural_attribution())

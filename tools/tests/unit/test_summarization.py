import sys
import os
import asyncio
import logging

# Setup paths
sys.path.append(os.getcwd())

# Mock config and logging if needed, or rely on imports
from utils.infrastructure.system.yaml_config import config
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import Intent, IntentParser

# Configure logging to stdout
logging.basicConfig(level=logging.INFO)

async def test_summarization():
    print("Initializing KaiaRAG and IntentParser...")
    import ollama
    client = ollama.AsyncClient()
    
    rag = KaiaRAG()
    parser = IntentParser(client, model=config.chat_model)
    
    query = "kaia summarize the transcript you have of the Three Buddy Problem podcast"
    print(f"\n--- Test 1: Intent Parsing (Query: '{query}') ---")
    intent = await parser.parse_intent(query)
    if intent and intent.suggested_strategy == "SUMMARIZATION":
        print(f"✅ Fast-path Intent Parsed Correctly: {intent.suggested_strategy}")
    else:
        print(f"❌ Intent Parsing Failed or Wrong Strategy: {intent.suggested_strategy if intent else 'None'}")
        # We'll continue with a manual intent for the RAG tests if this fails, 
        # but the failure itself is the bug.

    from utils.core.kaia_intelligence import ContextOptimizer
    
    # Use the parsed intent if it worked, otherwise manual
    test_intent = intent if (intent and intent.suggested_strategy == "SUMMARIZATION") else Intent(
        explicit_intent="Summarize transcript",
        implied_needs=["summary"],
        emotional_context="neutral",
        temporal_focus="present_immediate", 
        relational_context="general",
        suggested_strategy="SUMMARIZATION",
        confidence=1.0
    )
    
    print(f"\n--- Test 2: Full Document Retrieval (Strategy: {test_intent.suggested_strategy}) ---")
    
    query = "Summarize the Three Buddy Problem transcript"
    results = rag.retrieve(
        query=query, 
        intent=intent, 
        category="general", 
        top_k=5 
    )
    
    rag_text = ""
    if results:
        print(f"✅ Retrieved {len(results)} nodes.")
        rag_text = "\n\n".join([r['content'] for r in results])
        print(f"Total retrieved RAG text length: {len(rag_text)} chars")
    else:
        print("❌ No nodes retrieved.")

    print(f"\n--- Test 2: Context Window Boosting ---")
    optimizer = ContextOptimizer(model_name="gemma3:12b", max_tokens=24000) # Default small limit
    
    # Test Normal
    normal_opt = optimizer.optimize_context("general", "persona", [rag_text], [], strategy=None)
    print(f"Normal Strategy RAG length: {len(normal_opt['rag'])} chars")
    
    # Test Summarization
    sum_opt = optimizer.optimize_context("general", "persona", [rag_text], [], strategy="SUMMARIZATION")
    print(f"Summarization Strategy RAG length: {len(sum_opt['rag'])} chars")
    
    if len(sum_opt['rag']) > len(normal_opt['rag']):
         print("✅ SUCCESS: Context window boosted for summarization!")
    else:
         print("❌ FAILURE: Context window NOT boosted.")

    # 3. Direct Index Inspection (Debug)
    print("\n--- DEBUG: Direct Index Inspection ---")
    target_path_part = "Three Buddy Problem Episode 84 Transcript.md"
    found_nodes = []
    
    if 'knowledge' in rag.indices:
        print("Checking 'knowledge' index...")
        index = rag.indices['knowledge']
        all_docs = list(index.docstore.docs.values())
        print(f"Total docs in knowledge index: {len(all_docs)}")
        
        for n in all_docs:
            fpath = n.metadata.get('file_path', '')
            if target_path_part in fpath:
                found_nodes.append(n)
                
        print(f"Found {len(found_nodes)} nodes matching '{target_path_part}' in docstore.")
        if found_nodes:
            # Sort by chunk index if present
            found_nodes.sort(key=lambda x: x.metadata.get('chunk_index', -1))
            for i, n in enumerate(found_nodes):
                print(f"Node {i}: ID={n.node_id[:8]}... Chunk={n.metadata.get('chunk_index')} Length={len(n.get_content())}")
    else:
        print("'knowledge' index not found in RAG.")

if __name__ == "__main__":
    asyncio.run(test_summarization())

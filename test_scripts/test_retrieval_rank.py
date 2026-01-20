import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

async def test_rank():
    rag = KaiaRAG()
    query = "Tell me about Starkond the Prion"
    
    # We need to simulate the retrieval logic to get the enriched query
    query_lower = query.lower()
    known_users = []
    user_logs_path = os.path.join(rag.knowledge_base_dir, "user_logs")
    if os.path.exists(user_logs_path):
        for d in os.scandir(user_logs_path):
            if d.is_dir() and "_" in d.name:
                u_name = d.name.rsplit("_", 1)[0].replace("_", " ")
                known_users.append(u_name)
    
    detected_user = None
    for u_name in known_users:
        if u_name.lower() in query_lower:
            detected_user = u_name
            break
        for part in u_name.split():
            if len(part) > 3 and part.lower() in query_lower:
                detected_user = u_name
                break
        if detected_user: break
    
    enriched_query = query
    if detected_user:
        enriched_query = f"{query} user:{detected_user}"
    
    print(f"DEBUG: enriched_query='{enriched_query}'")
    
    retriever = rag.index.as_retriever(similarity_top_k=100)
    nodes = retriever.retrieve(enriched_query)
    
    print(f"Retrieved {len(nodes)} nodes.")
    for i, node_result in enumerate(nodes):
        node = node_result.node
        file_path = node.metadata.get('file_path', '')
        if 'Starkond' in file_path and 'user_profile.md' in file_path:
            print(f"FOUND at rank {i}! Score: {node_result.score}")
            print(f"Content: {node.get_content()[:100]}...")
        elif i < 5:
            print(f"Rank {i}: {node.metadata.get('user_name')} - {node.get_content()[:50]}...")

if __name__ == "__main__":
    asyncio.run(test_rank())

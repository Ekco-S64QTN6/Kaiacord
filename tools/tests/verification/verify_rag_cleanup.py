import os
import asyncio
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import Intent

async def verify():
    rag = KaiaRAG()
    
    queries = [
        "Gundam cartoons",
        "lefty catcher mitt jargon",
        "The Catcher in the Rye Mitt",
        "what have you been dreaming about kaia",
        "Kaia who are you?" # Should be gone from logs, but might find persona fragments
    ]
    
    print("\n--- EXTENDED VERIFICATION RESULTS ---")
    for q in queries:
        print(f"\nQuery: {q}")
        results = rag.retrieve(q, user_name="Ekco", top_k=3)
        if not results:
            print("  No nodes retrieved.")
            continue
            
        for i, res in enumerate(results):
            content = res['content']
            score = res['score']
            label = res['label']
            print(f"  [{i+1}] ({label}) Score: {score:.2f}")
            # Check for forbidden phrases in retrieved content
            forbidden = ["I'm a construct", "maintain the persona", "fourth wall", "not equipped to handle", "technical inquiries"]
            found = [f for f in forbidden if f.lower() in content.lower()]
            if found:
                print(f"  ❌ FOUND BROKEN CONTENT: {found}")
            else:
                print("  ✅ Content safe.")
            print(f"  Snippet: {content[:150].replace('\n', ' ')}...")

if __name__ == "__main__":
    asyncio.run(verify())

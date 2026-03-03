"""
Verify the system is clean after reset
"""

import asyncio
import ollama

async def test_kaia_responses():
    """Test Kaia with known problematic queries"""
    test_queries = [
        "kaia status",
        "kaia who are you",
        "kaia tell me about Trump and Iran",
        "kaia what do you remember",
        "kaia do you know anyone named Elena",
    ]
    
    print("🧪 Testing Kaia responses for contamination...")
    print("=" * 60)
    
    client = ollama.AsyncClient()
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        
        try:
            response = await client.chat(
                model="qwen3.5:9b",
                messages=[
                    {"role": "user", "content": query}
                ],
                options={"temperature": 0.3}
            )
            
            response_text = response['message']['content']
            
            # Check for contamination
            contamination_keywords = ["elena", "juanita", "deane", "bonbons", "agency"]
            
            clean = True
            for keyword in contamination_keywords:
                if keyword in response_text.lower():
                    print(f"🚨 CONTAMINATION FOUND: '{keyword}' in response!")
                    clean = False
            
            if clean:
                print("✅ Response is clean")
                print(f"   Preview: {response_text[:100]}...")
            else:
                print(f"   Full response: {response_text}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_kaia_responses())

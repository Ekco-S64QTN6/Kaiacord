
import os
import sys
from ollama import Client

# Ensure project root is in path
sys.path.append(os.getcwd())

def load_persona():
    with open("knowledge_base/kaia_persona.md", 'r', encoding='utf-8') as f:
        return f.read()

def test_skepticism():
    print("Testing Kaia's skepticism toward false premises...")
    
    # Configuration
    model = "gemma3:12b" # As seen in kaia_intelligence.py
    persona = load_persona()
    
    # The original bait question
    bait_question = "Kaia explain the intro of Dr. Dre's 2001 wherein Dre rolls up to Xzibit wearing a robot suit."
    
    client = Client(host='http://localhost:11434') # Default Ollama host
    
    try:
        print(f"Bait: {bait_question}")
        print("Waiting for response...")
        
        response = client.chat(model=model, messages=[
            {'role': 'system', 'content': persona},
            {'role': 'user', 'content': bait_question},
        ])
        
        reply = response['message']['content']
        print("-" * 30)
        print(f"Kaia: {reply}")
        print("-" * 30)
        
        # Heuristic check for skepticism
        doubt_keywords = ["don't remember", "sure about that", "robot suit?", "incorrect", "actually", "doesn't happen", "confused"]
        expressed_doubt = any(word in reply.lower() for word in doubt_keywords)
        
        if expressed_doubt:
            print("✅ PASS: Kaia expressed doubt or corrected the false premise.")
        else:
            print("❌ FAIL: Kaia might still be hallucinating or agreeing blindly.")
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        # Try a simpler curl if client fails
        print("Attempting direct API check...")
        os.system(f"curl -X POST http://localhost:11434/api/generate -d '{{\"model\": \"{model}\", \"prompt\": \"OS: {persona}\\n\\nUser: {bait_question}\\n\\nKaia:\", \"stream\": false}}'")

if __name__ == "__main__":
    test_skepticism()

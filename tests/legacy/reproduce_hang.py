import asyncio
import ollama
import sys
import os

# Add parent directory to path so we can import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.kaia_intelligence import QueryClassifier

async def main():
    print("Initializing Ollama client...")
    client = ollama.AsyncClient()
    
    print("Initializing QueryClassifier...")
    # Use the model name from the logs: gemma3:12b
    classifier = QueryClassifier(client, model_name="gemma3:12b")
    
    query = "kaia whats the recent news on AI breakthroughs"
    print(f"Classifying query: '{query}'")
    
    try:
        # Set a timeout to avoid indefinite hanging during test
        category = await asyncio.wait_for(classifier.classify(query), timeout=30)
        print(f"Classification result: {category}")
    except asyncio.TimeoutError:
        print("TIMEOUT: Classification timed out after 30 seconds!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

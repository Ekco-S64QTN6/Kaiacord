import os
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def list_gemini_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set.")
        return

    client = genai.Client(api_key=api_key)
    
    print("--- Available Gemini Models ---")
    try:
        # The new SDK might have a different way to list models
        # Let's try to list them
        # According to the docs/examples, searching models is done via models.list()
        for model in client.models.list():
            print(f"Model: {model.name}")
            print(f"  Supported Actions: {model.supported_actions}")
            print(f"  Input Token Limit: {model.input_token_limit}")
            print(f"  Output Token Limit: {model.output_token_limit}")
            print("-" * 30)
    except Exception as e:
        print(f"❌ Error listing models: {e}")

if __name__ == "__main__":
    list_gemini_models()

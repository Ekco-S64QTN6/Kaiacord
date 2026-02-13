import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def list_gemini_models():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not set.")
        return

    genai.configure(api_key=api_key)
    
    print("--- Available Gemini Models (GenerativeAI SDK) ---")
    try:
        for model in genai.list_models():
            print(f"Model: {model.name}")
            print(f"  Display Name: {model.display_name}")
            print(f"  Supported Methods: {model.supported_generation_methods}")
            print(f"  Input Token Limit: {model.input_token_limit}")
            print(f"  Output Token Limit: {model.output_token_limit}")
            print("-" * 30)
    except Exception as e:
        print(f"❌ Error listing models: {e}")

if __name__ == "__main__":
    list_gemini_models()

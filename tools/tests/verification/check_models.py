from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

print("Listing models...")
for m in genai.list_models():
    print(f"Name: {m.name}, Supported Methods: {m.supported_generation_methods}")

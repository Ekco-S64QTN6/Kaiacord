import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

print("Listing models...")
for m in genai.list_models():
    print(f"Name: {m.name}, Supported Methods: {m.supported_generation_methods}")

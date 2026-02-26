import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model_name = 'gemini-2.0-flash'
try:
    print(f"Testing {model_name} with grounding...")
    model = genai.GenerativeModel(model_name, tools='google_search_retrieval')
    response = model.generate_content("What is the latest news today?")
    print(f"✅ WITH GROUNDING: {model_name} SUCCESS! Output length: {len(response.text)}")
except Exception as e:
    print(f"❌ WITH GROUNDING: {model_name} FAILED: {str(e)}")

model_name_2 = 'gemini-2.5-flash'
try:
    print(f"Testing {model_name_2} with grounding...")
    model = genai.GenerativeModel(model_name_2, tools='google_search_retrieval')
    response = model.generate_content("What is the latest news today?")
    print(f"✅ WITH GROUNDING: {model_name_2} SUCCESS! Output length: {len(response.text)}")
except Exception as e:
    print(f"❌ WITH GROUNDING: {model_name_2} FAILED: {str(e)}")


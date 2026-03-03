import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

model_name = 'gemini-2.0-flash'
try:
    print(f"Testing {model_name} with grounding...")
    model = client.models
    response = model.generate_content("What is the latest news today?")
    print(f"✅ WITH GROUNDING: {model_name} SUCCESS! Output length: {len(response.text)}")
except Exception as e:
    print(f"❌ WITH GROUNDING: {model_name} FAILED: {str(e)}")

model_name_2 = 'gemini-2.5-flash'
try:
    print(f"Testing {model_name_2} with grounding...")
    model = client.models
    response = model.generate_content("What is the latest news today?")
    print(f"✅ WITH GROUNDING: {model_name_2} SUCCESS! Output length: {len(response.text)}")
except Exception as e:
    print(f"❌ WITH GROUNDING: {model_name_2} FAILED: {str(e)}")


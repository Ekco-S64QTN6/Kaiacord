import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

model_names = [
    'gemini-flash-latest',
    'gemini-1.5-flash',
    'gemini-1.5-pro-latest',
]

for name in model_names:
    try:
        model = client.models
        response = model.generate_content("What is the latest news today?")
        print(f"✅ WITH GROUNDING: {name} SUCCESS! Output length: {len(response.text)}")
    except Exception as e:
        print(f"❌ WITH GROUNDING: {name} FAILED: {str(e)[:100]}")

for name in model_names:
    try:
        model = client.models
        response = model.generate_content("What is the latest news today?")
        print(f"✅ NO GROUNDING: {name} SUCCESS! Output length: {len(response.text)}")
    except Exception as e:
        print(f"❌ NO GROUNDING: {name} FAILED: {str(e)[:100]}")

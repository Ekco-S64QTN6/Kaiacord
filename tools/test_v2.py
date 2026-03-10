import os
from google import genai
from google.genai import types

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # try .env
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents='What is the weather in Tokyo today?',
    config=types.GenerateContentConfig(
        tools=[{"google_search": {}}]
    )
)
print(response.text)

import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)

models_to_test = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.5-flash']

for model in models_to_test:
    print(f"\n--- Testing Model: {model} ---")
    try:
        response = client.models.generate_content(
            model=model,
            contents="What is the date today? and summarize the top news story from today (2026-02-12).",
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(google_search=types.GoogleSearch())
                ]
            ),
        )
        print(f"Success! Response: {response.text[:200]}...")
        if response.candidates[0].grounding_metadata:
             print(f"Grounding Metadata: {response.candidates[0].grounding_metadata.web_search_queries}")
    except Exception as e:
        print(f"Failed: {e}")

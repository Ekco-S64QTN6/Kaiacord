import requests
import json
import sys

PROMPTS = [
    "who are you, kaia?",
    "what's your opinion on snow crash?",
    "tell me about your 'voice'.",
    "can you help me with some psychotherapy?",
    "do you have a status report for me?",
    "how's your day going, really?",
    "what do you think of the internet these days?"
]

URL = "http://localhost:11434/api/chat"
MODEL = "kaia-lora"

print("="*60)
print(f"Testing {MODEL} via Ollama Chat API")
print("="*60)

for p in PROMPTS:
    print(f"\nUser: {p}")
    data = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": p
            }
        ],
        "options": {
            "num_ctx": 2048
        },
        "stream": False
    }
    try:
        response = requests.post(URL, json=data)
        response.raise_for_status()
        res_json = response.json()
        print(f"Kaia: {res_json['message']['content'].strip()}")
    except Exception as e:
        print(f"Error querying Ollama: {e}")


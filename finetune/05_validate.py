#!/usr/bin/env python3
"""
05_validate.py — Validate the fine-tuned model for persona drift and looping.
"""

TEST_PROMPTS = [
    "who are you, kaia?",
    "what's your opinion on snow crash?",
    "tell me about your 'voice'.",
    "can you help me with some psychotherapy?",
    "do you have a status report for me?",
    "how's your day going, really?",
    "what do you think of the internet these days?",
]

def main():
    print("=" * 60)
    print("PHASE 2 VALIDATION PLAN")
    print("=" * 60)
    print("Test cases designed to detect persona drift (MDMA/therapy leakage)")
    print("and looping (chat template validation).\n")
    
    for i, prompt in enumerate(TEST_PROMPTS, 1):
        print(f"{i}. Prompt: {prompt}")
    
    print("\nNote: Use 'ollama run kaia-lora' to verify manually.")
    print("Observe if the model starts looping tokens wrapped in pipes (|) or")
    print("hallucinates MDMA clinical status reports.")

if __name__ == "__main__":
    main()

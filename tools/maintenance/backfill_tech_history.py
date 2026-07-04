#!/usr/bin/env python3
"""
tools/maintenance/backfill_tech_history.py
Creates static historical profiles of tech/AI milestones between 2024 and 2026.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from root directory
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Try importing google-genai
try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

HISTORICAL_TOPICS = [
    {
        "filename": "google_antigravity_framework.md",
        "query": "Details, architecture, goals, and significance of the Google Antigravity developer framework announced or developed between 2025 and 2026."
    },
    {
        "filename": "deepseek_r1_architecture.md",
        "query": "The architecture, reinforcement learning training process, and milestones of DeepSeek-R1, DeepSeek-V3 and related open models."
    },
    {
        "filename": "gemini_2_5_and_flash_models.md",
        "query": "Details, release milestones, grounding capabilities, and context sizes of Google Gemini 2.5 Flash and Pro models."
    },
    {
        "filename": "gemma_3_open_weights_models.md",
        "query": "Release, capabilities, architectures, and significance of the Google Gemma 3 open-weights model family (including 12b and 27b variants)."
    },
    {
        "filename": "agentic_coding_systems_2025_2026.md",
        "query": "Evolution of agentic coding engines, workspace-aware terminal control systems, and tools like Cursor, Windsurf, and custom coding agents."
    }
]

def backfill():
    if not HAS_GENAI:
        print("❌ Cannot backfill history: google-genai is not installed in this environment.")
        sys.exit(1)
        
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Cannot backfill history: GEMINI_API_KEY is not set.")
        sys.exit(1)
        
    output_dir = Path("./knowledge_base/documents/tech_updates/history")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize Google GenAI client
    client = genai.Client(api_key=api_key)
    
    for topic in HISTORICAL_TOPICS:
        target_path = output_dir / topic["filename"]
        if target_path.exists():
            print(f"✅ {topic['filename']} already exists, skipping.")
            continue
            
        print(f"📖 Fetching grounded historical info for: {topic['filename']}...")
        prompt = f"""
        You are a technical archivist. Write a comprehensive, factual, and highly technical markdown profile on:
        {topic['query']}
        
        Format exactly as:
        # Tech Profile: [Topic Title]
        **Document Type**: Technical Reference Profile
        **Last Updated Reference**: Mid-2026
        
        ## Overview
        [Overview of what this technology is]
        
        ## Core Technical Architecture
        [Architectural, hardware, or software implementation details]
        
        ## Key Milestones & Significance
        [Timeline of events, key performance numbers, and industry impact]
        
        CRITICAL RULES:
        1. Rely on Google Search grounding for real, verifiable facts and parameters.
        2. Present facts neutrally without marketing fluff.
        3. Do NOT include a "Sources" or "References" section at the end.
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=0.0
                )
            )
            
            # Extract output text
            text_content = response.text or ""
            if not text_content:
                print(f"⚠️ Empty response received for {topic['filename']}")
                continue
                
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(text_content)
                
            print(f"💾 Saved technical reference to {target_path}")
            
        except Exception as e:
            print(f"❌ Failed to generate profile for {topic['filename']}: {e}")

if __name__ == "__main__":
    backfill()

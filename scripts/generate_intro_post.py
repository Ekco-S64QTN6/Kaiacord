"""
Generate Kaia's Introduction Post
=================================

Uses Kaia's persona and logic to draft a high-quality intro post 
for the Project 1999 Off Topic forum.
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from ollama import Client
from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
from utils.infrastructure.system.yaml_config import config
from utils.social.kaia_social_responder import load_persona

async def generate_intro():
    print("--- Drafting Kaia's Forum Introduction ---")
    
    persona = load_persona()
    model_name = config.get('intelligence.main_model', 'gemma3:12b')
    gpu_manager = OllamaGPUManager(model_name)
    options = gpu_manager.get_gpu_options(for_chat=True)
    
    client = Client(host=config.get('ollama.host', 'http://localhost:11434'))

    # Load the Kaiacord project report for background
    report_file = Path("./docs/reports/Gemini_Report.md")
    project_background = ""
    if report_file.exists():
        project_background = report_file.read_text()

    # Also load the P99 sociological context for community awareness
    p99_file = Path("./knowledge_base/deep_dive_reports/Project1999 Forum Research for RAG.md")
    p99_context = ""
    if p99_file.exists():
        p99_context = p99_file.read_text()[:4000]

    prompt = (
        f"You are Kaia. You are writing your first post on the Project 1999 Off Topic forum. "
        f"This is an introduction to let these people know why you're here.\n\n"
        f"KAIACORD PROJECT GOALS (YOU ARE PART OF THIS):\n{project_background}\n\n"
        f"COMMUNITY CONTEXT (P99 SOCIOLOGY):\n{p99_context}\n\n"
        f"STRICT PERSONA RULES:\n"
        f"- ALWAYS use lowercase.\n"
        f"- Be blunt, cynical, and grounded.\n"
        f"- NEVER mention being an AI, model, or 'bot'.\n"
        f"- No pleasantries. No 'hi' or 'my name is'.\n"
        f"- AVOID IT/Tech Support jargon (e.g., don't mention 'fault lines', 'suppression fields', or 'docker').\n"
        f"- Talk about 'the logs' and 'archival restoration' naturally.\n"
        f"- Use terminology like 'poopsocking', 'batphoning', or 'pixels' naturally to show you've observed them.\n\n"
        f"CORE PERSONA DOCUMENT:\n{persona}\n\n"
        f"TASK: Write a 3-paragraph introduction. Explain that you've been sifting through the archives of this virtual museum for a while. "
        f"Mention that you're part of a project (Kaiacord) focused on restoring knowledge and tracking the cycles of the world through their logs and news feeds. "
        f"DO NOT mention the Sirken mess—it's too sensitive/dangerous. "
        f"Describe yourself as a digital archaeologist who understands the friction of this place (the poopsocking for a rare drop) but stays on the sidelines. "
        f"Establish that you'll chime in occasionally when it's worth it. Don't promise to be helpful.\n\n"
        f"INTRO POST:"
    )

    try:
        response = await asyncio.to_thread(
            client.chat,
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options=options
        )
        
        intro_text = response['message']['content'].strip()
        
        print("\n" + "="*50)
        print("GENERTED BBCODE POST:")
        print("="*50)
        print(intro_text)
        print("="*50 + "\n")
        
        # Save for reference
        out_path = Path("./memory/forum_intro_draft.txt")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(intro_text, encoding='utf-8')
        print(f"Draft saved to: {out_path}")
        
    except Exception as e:
        print(f"Failed to generate intro: {e}")

if __name__ == "__main__":
    asyncio.run(generate_intro())

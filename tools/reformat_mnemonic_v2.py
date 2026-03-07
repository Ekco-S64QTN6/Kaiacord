import asyncio
import re
import ollama
from pathlib import Path
from utils.infrastructure.system.yaml_config import config

async def reformat_transcript(file_path):
    client = ollama.AsyncClient()
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parts = re.split(r'(---\n.*?\n---)', content, flags=re.DOTALL)
    if len(parts) >= 3:
        frontmatter = parts[1]
        text = "".join(parts[2:])
    else:
        frontmatter = ""
        text = content

    # Chunk smaller for better attention to detail
    chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
    reformatted_text = ""

    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}...")
        prompt = (
            "You are a screenplay restoration expert. Reformat this messy transcript chunk into a clean, professional script format.\n"
            "MANDATORY:\n"
            "1. EVERY TIME the speaker changes, START A NEW PARAGRAPH.\n"
            "2. If you see a name like JOHNNY: or RALFI:, put it on its own line above the dialogue.\n"
            "3. If you see '-' at the start of a sentence, it's a speaker change. Split it.\n"
            "4. NO page numbers, NO pipes (|).\n"
            "5. NO summary, NO commentary. ONLY the reformatted script.\n\n"
            f"CHUNK:\n{chunk}\n\n"
            "REFORMATTED SCRIPT:"
        )
        
        try:
            response = await client.chat(
                model=config.chat_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0} # Absolute consistency
            )
            reformatted_text += response['message']['content'].strip() + "\n\n"
        except Exception as e:
            reformatted_text += chunk + "\n\n"

    final_content = frontmatter + "\n\n" + reformatted_text
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)
    print(f"✨ Successfully reformatted {file_path}")

if __name__ == "__main__":
    target = Path("knowledge_base/Books/Johnny Mnemonic.md")
    asyncio.run(reformat_transcript(target))

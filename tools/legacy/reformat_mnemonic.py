import asyncio
import re
import ollama
from pathlib import Path
from utils.infrastructure.system.yaml_config import config

async def reformat_transcript(file_path):
    client = ollama.AsyncClient()
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into frontmatter and text
    parts = re.split(r'(---\n.*?\n---)', content, flags=re.DOTALL)
    if len(parts) >= 3:
        frontmatter = parts[1]
        text = "".join(parts[2:])
    else:
        frontmatter = ""
        text = content

    # Chunk the text (approx 4000 chars per chunk to avoid timeout and retain context)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    reformatted_chunks = []

    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i+1}/{len(chunks)}...")
        prompt = (
            "You are a script formatting expert. Reformat the following movie transcript into a clean, readable screenplay format.\n"
            "GUDIELINES:\n"
            "1. Separate different speakers into new paragraphs.\n"
            "2. DO NOT use 'few words per line' - use full sentences and readable paragraphs for dialogue.\n"
            "3. Ensure character names are clear if present, or use dialogue dashes (-) if you can't tell the speaker.\n"
            "4. Keep it concise but complete. DO NOT summarize.\n"
            "5. NO page numbers or pipe characters.\n\n"
            f"TRANSCRIPT CHUNK:\n{chunk}\n\n"
            "REFORMATTED SCRIPT:"
        )
        
        response = await client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}
        )
        reformatted_chunks.append(response['message']['content'].strip())

    final_text = frontmatter + "\n\n" + "\n\n".join(reformatted_chunks)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_text)
    print(f"✨ Successfully reformatted {file_path}")

if __name__ == "__main__":
    target = Path("knowledge_base/Books/Johnny Mnemonic.md")
    asyncio.run(reformat_transcript(target))

import asyncio
from utils.infrastructure.logging.kaia_logger import log_warning

async def send_kaia_response(channel, text, use_code_block=True):
    """Helper to split long messages and optionally wrap them in Kaia's code block style"""
    if not text:
        log_warning("send_kaia_response called with empty text. Skipping.")
        return
        
    # Discord limit is 2000. 
    # Use 1980 for code blocks to leave room for ```\n and \n```
    # Use 1990 for plain text for a small safety margin.
    limit = 1980 if use_code_block else 1990
    
    if len(text) <= limit:
        if use_code_block:
            await channel.send(f"```\n{text.strip()}\n```")
        else:
            await channel.send(text.strip())
        return

    # Split into chunks
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        if len(current_chunk) + len(line) + 1 > limit:
            chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    for chunk in chunks:
        if not chunk: continue
        if use_code_block:
            await channel.send(f"```\n{chunk}\n```")
        else:
            await channel.send(chunk)
        await asyncio.sleep(0.5) # Prevent rate limiting

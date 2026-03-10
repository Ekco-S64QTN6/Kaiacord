"""
Self-Model Generation Command
=============================

!selfmodel — Regenerate the kaia_self_model.md file on demand.
"""

import os
import asyncio
import sys
from utils.infrastructure.logging.kaia_logger import log_info, log_error

async def handle_selfmodel_command(ctx, msg, send_kaia_response):
    """Handle the !selfmodel command to trigger self-model regeneration."""
    await send_kaia_response(msg.channel, "Reflecting on recent memories... Regenerating self-model. This may take a moment.")
    log_info(f"Self-model regeneration triggered by {msg.author.name}")

    try:
        # Run the generation script as a subprocess
        script_path = os.path.join("tools", "development", "generate_self_model.py")
        
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            log_error(f"Self-model generation failed: {error_msg}")
            await send_kaia_response(msg.channel, f"Failed to regenerate self-model: {error_msg[:200]}")
            return
            
        # Read the newly generated model for confirmation
        self_model_path = os.path.join("memory", "kaia_self_model.md")
        if os.path.exists(self_model_path):
            with open(self_model_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                
            # Strip the HTML comment header if present
            if content.startswith('<!--'):
                content = content[content.find('-->')+3:].strip()
                
            preview = content[:300] + ("..." if len(content) > 300 else "")
            await send_kaia_response(msg.channel, f"Self-model updated successfully.\n\n**Preview:**\n{preview}")
            log_info("Self-model regenerated successfully.")
        else:
            await send_kaia_response(msg.channel, "Self-model script completed, but output file was not found.")
            log_error("Self-model output file missing after script completion.")
            
    except Exception as e:
        log_error(f"Error executing self-model generation: {e}")
        await send_kaia_response(msg.channel, f"An error occurred while regenerating the self-model: {e}")

import asyncio
import sys
import os
from pathlib import Path
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info

async def handle_enrich_command(ctx, msg, send_kaia_response):
    """Handle the !enrich command (Admin only) — trigger metadata enrichment for the knowledge base."""
    
    # Owner exemption - uses configurable owner_ids from config
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    
    if not is_owner:
        await msg.channel.send("```\nrestricted. this command is for admins only.\n```")
        return

    parts = msg.content.strip().split()
    category = "all"
    is_dry_run = False
    
    # Simple arg parsing for Discord
    if "--dry-run" in parts:
        is_dry_run = True
    
    if "--category" in parts:
        try:
            idx = parts.index("--category")
            if idx + 1 < len(parts):
                category = parts[idx + 1].lower()
                if category not in ["all", "knowledge", "logs"]:
                    await msg.channel.send("```\ninvalid category. use 'all', 'knowledge', or 'logs'.\n```")
                    return
        except ValueError:
            pass

    status_msg = await msg.channel.send(f"🔄 **Starting Metadata Enrichment** (Category: `{category}`, Dry-run: `{is_dry_run}`)...")
    log_action(f"Admin {msg.author.display_name} triggered !enrich (category={category}, dry_run={is_dry_run})")

    try:
        # Resolve path to the script
        script_path = Path("./tools/maintenance/enrich_metadata.py").absolute()
        if not script_path.exists():
            await status_msg.edit(content="```\nerror: enrichment script not found at ./tools/maintenance/enrich_metadata.py\n```")
            return

        # Build command
        cmd = [sys.executable, str(script_path), "--category", category]
        if is_dry_run:
            cmd.append("--dry-run")

        # Run as subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        
        # Parse output for summary
        output_str = stdout.decode().strip()
        error_str = stderr.decode().strip()
        
        if error_str:
            log_error(f"!enrich subprocess error: {error_str}")

        # Extract stats from the output if possible using regex or just show last few lines
        # The script prints stats at the end.
        summary_lines = []
        capture = False
        for line in output_str.split('\n'):
            if "--- ENRICHMENT COMPLETED ---" in line:
                capture = True
                continue
            if capture:
                summary_lines.append(line)

        if not summary_lines:
            # Fallback if parsing fails
            summary = "Enrichment completed, but summary parsing failed. Check server logs."
        else:
            summary = "\n".join(summary_lines)

        await status_msg.edit(content=f"✅ **Enrichment Complete**\n```\n{summary}\n```")
        log_info(f"!enrich completed for {msg.author.display_name}")

    except Exception as e:
        log_error(f"Failed to run !enrich command: {e}")
        await status_msg.edit(content=f"```\nerror during enrichment: {str(e)}\n```")

import asyncio
import sys
import os
import re
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
    category = "knowledge"  # Default to knowledge only (Fix 5)
    is_dry_run = False
    limit = 50
    
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

    if "--limit" in parts:
        try:
            idx = parts.index("--limit")
            if idx + 1 < len(parts):
                limit = int(parts[idx + 1])
        except (ValueError, IndexError):
            pass

    status_msg = await msg.channel.send(f"🔄 **Starting Metadata Enrichment** (Category: `{category}`, Limit: `{limit}`, Dry-run: `{is_dry_run}`)...")
    log_action(f"Admin {msg.author.display_name} triggered !enrich (category={category}, limit={limit}, dry_run={is_dry_run})")

    try:
        # Project root resolution
        project_root = Path(__file__).parent.parent.parent
        script_path = project_root / "tools" / "maintenance" / "enrich_metadata.py"
        
        if not script_path.exists():
            await status_msg.edit(content="```\nerror: enrichment script not found at tools/maintenance/enrich_metadata.py\n```")
            return

        # Build command
        cmd = [sys.executable, str(script_path.absolute()), "--category", category, "--limit", str(limit)]
        if is_dry_run:
            cmd.append("--dry-run")

        # Run as subprocess with explicit cwd (Fix 2)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_root)
        )

        # Fix 1: Subprocess timeout and progress updates using a heartbeat task
        start_time = asyncio.get_event_loop().time()
        max_timeout = 600.0
        
        async def _progress_updater():
            while True:
                await asyncio.sleep(60)
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                try:
                    await status_msg.edit(content=f"🔄 **Enrichment in progress...** ({elapsed}s elapsed)")
                except Exception:
                    break

        progress_task = asyncio.create_task(_progress_updater())
        
        try:
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=max_timeout)
            except asyncio.TimeoutError:
                if process.returncode is None:
                    try: 
                        process.terminate()
                        await process.wait()
                    except: pass
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                await status_msg.edit(content=f"❌ **Enrichment Timed Out** (after {elapsed}s). Run from terminal for large batches.")
                return
        finally:
            progress_task.cancel()

        # Parse output for summary (Fix 1: ANSI + \r stripping)
        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
        # Replace \r with \n to handle progress line accumulation (Fix 2)
        output_str = ansi_escape.sub('', stdout.decode()).replace('\r', '\n').strip()
        error_str = stderr.decode().strip()
        
        if error_str:
            log_error(f"!enrich subprocess error: {error_str}")

        # Extract stats from the clean output
        summary_lines = []
        capture = False
        all_lines = [l.strip() for l in output_str.split('\n') if l.strip()]
        
        for line in all_lines:
            if "--- ENRICHMENT COMPLETED ---" in line:
                capture = True
                continue
            if capture:
                summary_lines.append(line)

        if not summary_lines:
            # Fallback: last 15 non-empty lines if marker not found
            summary = "\n".join(all_lines[-15:])
        else:
            summary = "\n".join(summary_lines)

        if not summary:
            summary = "Enrichment completed, but no output was captured."

        await status_msg.edit(content=f"✅ **Enrichment Complete**\n```\n{summary}\n```")
        log_info(f"!enrich completed for {msg.author.display_name}")

    except Exception as e:
        log_error(f"Failed to run !enrich command: {e}")
        await status_msg.edit(content=f"```\nerror during enrichment: {type(e).__name__}: {str(e)}\n```")

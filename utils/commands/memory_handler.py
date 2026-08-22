import re
import os
import json
import asyncio
import discord
from utils.infrastructure.logging.kaia_logger import log_action

async def handle_memory_command(msg, sanitized_content, run_rag, rag):
    """Handle the 'kaia remember' command"""
    # This regex ensures that only explicit "kaia remember [this/that]:" triggers the log
    # It prevents "remember when..." questions from being logged.
    remember_match = re.match(r"kaia remember (?:this|that|to|the following)?:?\s*(.*)", sanitized_content, re.IGNORECASE)
    if remember_match and not re.search(r"\bwhen\b|\bif\b|\bhow\b", sanitized_content, re.IGNORECASE):
        memory_content = remember_match.group(1).strip()
        if memory_content:
            log_action(f"Storing memory: {memory_content}")
            if run_rag and rag:
                success = await run_rag(rag.add_memory, msg.author.id, msg.author.display_name, memory_content)
                if success:
                    await msg.channel.send("```\nLogged it.\n```")
                else:
                    await msg.channel.send("```\nMemory buffer error. Try again.\n```")
        else:
            await msg.channel.send("```\nRemember what? I'm not a mind reader.\n```")
        return True
    return False

def _load_beliefs_sync() -> list:
    beliefs_path = os.path.join("memory", "beliefs.json")
    if os.path.exists(beliefs_path):
        try:
            with open(beliefs_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def _load_anchors_sync() -> list:
    anchors_path = os.path.join("memory", "anchors.json")
    if os.path.exists(anchors_path):
        try:
            with open(anchors_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

async def handle_memory_cmd(ctx, msg, send_kaia_response):
    """Handle the !memory command (Admin only)"""
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    if not is_owner:
        await msg.channel.send("```\nyou aren't my architect. restricted.\n```")
        return

    parts = msg.content.strip().split()
    subcommand = parts[1].lower() if len(parts) > 1 else ""

    if subcommand == "beliefs":
        beliefs = await asyncio.to_thread(_load_beliefs_sync)
        if not beliefs:
            embed = discord.Embed(
                title="🧠  KAIA'S ACTIVE BELIEFS",
                description="No active beliefs stored yet in beliefs.json.",
                color=0x3b82f6
            )
            await msg.channel.send(embed=embed)
            return

        embed = discord.Embed(
            title="🧠  KAIA'S ACTIVE BELIEFS",
            description=f"Active belief-state vectors extracted from daily reflections (Total: {len(beliefs)} / 100 cap).",
            color=0x3b82f6
        )

        shown_count = 0
        for i, b in enumerate(beliefs, 1):
            topic = b.get('topic', 'unknown')
            conf = b.get('confidence', 0.5)
            pos = b.get('position', '')
            if len(pos) > 180:
                pos = pos[:177] + "..."
            
            embed.add_field(
                name=f"{i}. {topic.upper()} (Confidence: {conf:.2f})",
                value=f"*{pos}*",
                inline=False
            )
            shown_count += 1
            if len(embed.fields) >= 20:
                break
                
        if shown_count < len(beliefs):
            embed.set_footer(text=f"... and {len(beliefs) - shown_count} more beliefs · Kaia System")
        else:
            embed.set_footer(text="Kaia System Belief Engine")

        await msg.channel.send(embed=embed)

    elif subcommand == "anchors":
        anchors = await asyncio.to_thread(_load_anchors_sync)
        if not anchors:
            embed = discord.Embed(
                title="⚓  KAIA'S EPISODIC MEMORY ANCHORS",
                description="No episodic anchors stored yet in anchors.json.",
                color=0x8b5cf6
            )
            await msg.channel.send(embed=embed)
            return

        embed = discord.Embed(
            title="⚓  KAIA'S EPISODIC MEMORY ANCHORS",
            description=f"Episodic memory anchors tracked across conversation loops (Total: {len(anchors)} / 100 cap).",
            color=0x8b5cf6
        )

        shown_count = 0
        for i, a in enumerate(anchors, 1):
            theme = a.get('theme', 'unknown')
            user = a.get('user_name') or 'general'
            weight = a.get('effective_weight') or a.get('weight', 0.5)
            text = a.get('anchor_text', '')
            if len(text) > 180:
                text = text[:177] + "..."
                
            embed.add_field(
                name=f"{i}. Theme: {theme} (Weight: {weight:.2f})",
                value=f"**User:** {user}\n*\"{text}\"*",
                inline=False
            )
            shown_count += 1
            if len(embed.fields) >= 20:
                break
                
        if shown_count < len(anchors):
            embed.set_footer(text=f"... and {len(anchors) - shown_count} more anchors · Kaia System")
        else:
            embed.set_footer(text="Kaia System Episodic Memory")

        await msg.channel.send(embed=embed)

    else:
        # Show usage help
        embed = discord.Embed(
            title="🧠  KAIA MEMORY ENGINE",
            description="Access controls and listings for Kaia's cognitive storage databases.",
            color=0x5f5caf
        )
        embed.add_field(
            name="Usage",
            value=(
                "`!memory beliefs` — View active revisable beliefs (100-cap)\n"
                "`!memory anchors` — View episodic memory anchors (100-cap)"
            ),
            inline=False
        )
        await msg.channel.send(embed=embed)

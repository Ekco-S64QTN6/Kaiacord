"""
Knowledge Source Provenance Display
====================================

!explain — Show which RAG nodes informed the last response,
           including their scores, audit flags, and sources.
"""

import os
import time
import discord
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_info


async def handle_explain_command(ctx, msg, send_kaia_response):
    """Handle the !explain command — display provenance of last RAG retrieval (Admin only)."""
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    if not is_owner:
        await msg.channel.send("```\nyou aren't my architect. restricted.\n```")
        return

    rag = ctx.rag
    if not rag:
        embed = discord.Embed(
            title="📚  PROVENANCE ERROR",
            description="RAG retrieval system is currently unavailable.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    results = getattr(rag, '_last_retrieval_results', [])

    if not results:
        embed = discord.Embed(
            title="📚  KNOWLEDGE SOURCE PROVENANCE",
            description="No recent retrieval to explain. Ask me something first.",
            color=0x5f5caf
        )
        await msg.channel.send(embed=embed)
        return

    # --- Pre-resolve summary values ---

    confidence = getattr(rag, '_last_retrieval_confidence', 0.0)

    # Confidence label
    if confidence >= 0.75:
        conf_label = "high"
    elif confidence >= 0.45:
        conf_label = "moderate"
    else:
        conf_label = "low"

    # Recency stats (newest/oldest)
    all_dates = []
    for node in results:
        fpath = node.get("metadata", {}).get("file_path", "")
        if fpath and os.path.exists(fpath):
            try: all_dates.append(os.path.getmtime(fpath))
            except: pass

    recency_info = "unknown"
    if all_dates:
        newest = datetime.fromtimestamp(max(all_dates)).strftime("%Y-%m-%d")
        oldest = datetime.fromtimestamp(min(all_dates)).strftime("%Y-%m-%d")
        recency_info = f"{oldest} → {newest}"

    # Self-model status
    self_model_path = os.path.join("memory", "kaia_self_model.md")
    if os.path.exists(self_model_path):
        sm_age = (time.time() - os.path.getmtime(self_model_path)) / 86400
        sm_status = f"active ({sm_age:.0f}d ago)"
    else:
        sm_status = "inactive"

    # --- Build Embed ---

    embed = discord.Embed(
        title="📚  KNOWLEDGE SOURCE PROVENANCE",
        description=f"Confidence rating: **{confidence:.2f} ({conf_label})** · Showing top {min(8, len(results))} of {len(results)} nodes.",
        color=0x10b981
    )

    # Show top 8 sources instead of 5
    top_results = results[:8]
    node_lines = []

    # Build lines with ANSI coloring
    ESC = "\u001b"
    RESET = f"{ESC}[0m"

    for i, node in enumerate(top_results, 1):
        metadata = node.get("metadata", {})
        score    = node.get("score", 0.0)
        source_type       = metadata.get("source_type", "unknown")
        retrieval_method  = metadata.get("retrieval_method", "unknown")
        audit_flags       = metadata.get("audit_flags", [])
        file_path         = metadata.get("file_path", "")
        basename          = os.path.basename(file_path) if file_path else "unknown"

        # Determine relative path from knowledge_base for all folders
        display_path = basename
        is_user_log = False
        parsed_username = ""
        is_profile = False

        if file_path:
            norm_path = os.path.normpath(file_path)
            parts = norm_path.split(os.sep)
            if "knowledge_base" in parts:
                try:
                    kb_idx = parts.index("knowledge_base")
                    rel_parts = parts[kb_idx + 1:]
                    if rel_parts:
                        if len(rel_parts) >= 2 and rel_parts[0] == "user_logs":
                            is_user_log = True
                            user_folder = rel_parts[1]
                            if "_" in user_folder:
                                parsed_username = user_folder.split("_")[0]
                            else:
                                parsed_username = user_folder
                            if "user_profile.md" in basename:
                                is_profile = True
                        display_path = "/".join(rel_parts)
                except ValueError:
                    pass
            elif "user_logs" in parts:
                try:
                    ul_idx = parts.index("user_logs")
                    rel_parts = parts[ul_idx:]
                    if len(rel_parts) >= 2:
                        is_user_log = True
                        user_folder = rel_parts[1]
                        if "_" in user_folder:
                            parsed_username = user_folder.split("_")[0]
                        else:
                            parsed_username = user_folder
                        if "user_profile.md" in basename:
                            is_profile = True
                        display_path = "/".join(rel_parts)
                except ValueError:
                    pass

        # Select method color
        method_upper = retrieval_method.upper()
        if method_upper == "HYBRID":
            method_color = f"{ESC}[1;35m" # Bold Magenta
        elif method_upper == "VECTOR":
            method_color = f"{ESC}[1;36m" # Bold Cyan
        elif method_upper == "BM25":
            method_color = f"{ESC}[1;34m" # Bold Blue
        else:
            method_color = f"{ESC}[1;37m" # Bold White

        # Format display name/path
        if is_user_log:
            log_type = "profile" if is_profile else "log"
            path_str = f"{ESC}[1;32m- {parsed_username} - [{log_type}]{RESET}"
        elif display_path == "unknown":
            path_str = f"{ESC}[1;31munknown{RESET}"
        else:
            if len(display_path) > 38:
                display_path = display_path[:18] + "…" + display_path[-19:]
            path_str = f"{ESC}[0;37m{display_path}{RESET}"

        flag_str = f" {ESC}[1;31m[⚑ {', '.join(audit_flags)}]{RESET}" if audit_flags else ""

        line = f"{ESC}[1;37m#{i}{RESET} · {ESC}[1;33m{score:.3f}{RESET} {method_color}({method_upper}){RESET} -> {path_str}{flag_str}"
        node_lines.append(line)

    # Ensure field value stays safely within Discord's 1024-character limit
    valid_lines = []
    current_chars = len("```ansi\n\n```")
    for line in node_lines:
        if current_chars + len(line) + 1 > 1000:
            break
        valid_lines.append(line)
        current_chars += len(line) + 1

    embed.description = f"Confidence rating: **{confidence:.2f} ({conf_label})** · Showing top {len(valid_lines)} of {len(results)} nodes."

    # Build field value with hard safety cap to prevent Discord 50035 overflow
    if valid_lines:
        field_value = "```ansi\n" + "\n".join(valid_lines) + "\n```"
    else:
        field_value = "```\nNo sources available\n```"

    # Absolute hard cap — ANSI escape codes are invisible but counted by Discord API
    if len(field_value) > 1020:
        field_value = field_value[:1017] + "```"

    embed.add_field(
        name="Sources & Relevance Scores",
        value=field_value,
        inline=False
    )

    embed.set_footer(text=f"Range: {recency_info}  ·  Self-model: {sm_status}")

    try:
        await msg.channel.send(embed=embed)
    except discord.HTTPException as e:
        # Fallback: send plain text summary if Discord rejects the embed
        log_info(f"Embed send failed ({e.status}/{e.code}), falling back to plain text.")
        fallback_lines = [f"#{i+1} · {r.get('score', 0):.3f} — {os.path.basename(r.get('metadata', {}).get('file_path', 'unknown'))}"
                          for i, r in enumerate(results[:8])]
        await msg.channel.send(f"**📚 PROVENANCE** (plain text fallback)\nConfidence: {confidence:.2f} ({conf_label})\n" + "\n".join(fallback_lines))
    log_info(f"Provenance display shown for {msg.author.name}")

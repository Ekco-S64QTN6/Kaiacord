"""
Conversation Memory Snapshots
=============================

!snapshot — Capture the current conversation as a structured RAG node
           tagged with participants, date, topic, and channel.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from utils.infrastructure.logging.kaia_logger import log_action, log_info, log_error, log_success


async def handle_snapshot_command(ctx, msg, send_kaia_response):
    """Handle the !snapshot command — distill current conversation into a persistent RAG node."""
    from utils.infrastructure.system.yaml_config import config

    if not config.get('features.snapshots_enabled', True):
        await send_kaia_response(msg.channel, "Snapshots are currently disabled.")
        return

    message_count = config.get('snapshots.message_count', 50)

    try:
        # Fetch recent messages from the channel
        messages = []
        async for m in msg.channel.history(limit=message_count):
            if m.content and m.content.strip():
                messages.append(m)
        messages.reverse()  # Oldest first

        if len(messages) < 3:
            await send_kaia_response(msg.channel, "Not enough conversation to snapshot.")
            return

        # Extract participants
        participants = sorted(set(m.author.display_name for m in messages))

        # Extract topic from first substantial message (skip bot commands)
        topic = "General Discussion"
        for m in messages[:10]:
            if m.author.bot:
                continue
            text = m.content.strip()
            if not text.startswith("!") and len(text) > 20:
                # Use first ~80 chars as topic summary
                topic = text[:80].replace("\n", " ")
                if len(text) > 80:
                    topic += "..."
                break

        # Sanitize topic for safe insertion into confirmation block
        topic_safe = topic.replace("`", "'").replace("*", "").replace("_", "")

        # Build the snapshot content
        channel_name = getattr(msg.channel, 'name', 'DM')
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d %H:%M")
        file_date = timestamp.strftime("%Y%m%d_%H%M%S")

        # Build structured Markdown
        lines = [
            "---",
            f'title: "Conversation Snapshot — {date_str}"',
            f'date: "{date_str}"',
            f'participants: [{", ".join(participants)}]',
            f'channel: "{channel_name}"',
            f'topic: "{_escape_yaml(topic)}"',
            f'document_type: Snapshot',
            "---",
            "",
            f"# Conversation Snapshot — {date_str}",
            f"**Channel:** {channel_name}",
            f"**Participants:** {', '.join(participants)}",
            f"**Topic:** {topic}",
            "",
            "---",
            "",
        ]

        # Add conversation content
        for m in messages:
            msg_time = m.created_at.strftime("%H:%M")
            author = m.author.display_name
            content = m.content.replace("\n", "\n> ")
            lines.append(f"**[{msg_time}] {author}:** {content}")
            lines.append("")

        snapshot_text = "\n".join(lines)

        # Save to knowledge_base/snapshots/
        kb_dir = config.get('paths.knowledge_base', './knowledge_base')
        snapshot_dir = os.path.join(kb_dir, "snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)

        filename = f"snapshot_{file_date}.md"
        filepath = os.path.join(snapshot_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(snapshot_text)

        log_success(f"Snapshot saved: {filename}")

        # Trigger reindex
        _trigger_reindex()

        await send_kaia_response(
            msg.channel,
            f"snapshot saved — {len(messages)} messages captured.\n"
            f"participants: {', '.join(participants)}\n"
            f"topic: {topic_safe}"
        )

    except Exception as e:
        log_error(f"Snapshot failed: {e}")
        await send_kaia_response(msg.channel, "Failed to create snapshot. Check logs.")


def _escape_yaml(text: str) -> str:
    """Escape text for safe YAML string values."""
    return text.replace('"', '\\"').replace("\n", " ")


def _trigger_reindex():
    """Touch the trigger file so RAG picks up new content."""
    try:
        Path(".trigger_reindex").touch()
    except Exception:
        pass

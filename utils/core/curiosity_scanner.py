"""
Curiosity Scanner
=================
Scans a user's recent interaction logs for unresolved mentions.
Returns a short follow-up prompt string if something worth asking about is found.

Usage:
    from utils.core.curiosity_scanner import get_curiosity_prompt
    prompt = get_curiosity_prompt(user_id, user_name, knowledge_base_dir)
    if prompt:
        # inject prompt into system context
"""

import os
import re
import glob
import time
from typing import Optional
from utils.infrastructure.logging.kaia_logger import log_debug

# Patterns that suggest something unresolved — user expressed intent or pending action
_UNRESOLVED_PATTERNS = [
    re.compile(r"\bi'?ll\s+(?:let you know|update you|check|test|try|look into|fix|get back)\b", re.IGNORECASE),
    re.compile(r"\blet me know how\b", re.IGNORECASE),
    re.compile(r"\bgoing to\s+(?:try|check|fix|test|look into|work on|start|finish|build|run)\b", re.IGNORECASE),
    re.compile(r"\bwill\s+(?:try|check|look|test|fix|update|work on)\b", re.IGNORECASE),
    re.compile(r"\b(?:working on|thinking about|planning to|hoping to)\b", re.IGNORECASE),
    re.compile(r"\bget back to you\b", re.IGNORECASE),
    re.compile(r"\bfollow up\b", re.IGNORECASE),
    re.compile(r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE),
]

# Patterns that suggest resolution — the thing was completed or closed
_RESOLVED_PATTERNS = [
    re.compile(r"\b(?:it worked|fixed it|done|finished|completed|solved|resolved)\b", re.IGNORECASE),
    re.compile(r"\bended up\b", re.IGNORECASE),
    re.compile(r"\bturned out\b", re.IGNORECASE),
]

_COOLDOWN_SECONDS = 48 * 3600  # 48 hours minimum between curiosity prompts per user
_MAX_LOG_CHARS = 8000           # How much of the log to scan


def get_curiosity_prompt(user_id: str, user_name: str, knowledge_base_dir: str,
                          last_sent_timestamps: dict) -> Optional[str]:
    """
    Scan user's recent interaction logs for unresolved mentions.
    
    Args:
        user_id: Discord user ID string.
        user_name: Display name for log path matching.
        knowledge_base_dir: Root of the knowledge_base directory.
        last_sent_timestamps: Dict of {user_id: timestamp} from bot_state.curiosity_last_sent.
    
    Returns:
        A prompt injection string like "[follow-up note: user mentioned X — ask if natural]",
        or None if nothing found or cooldown hasn't passed.
    """
    # Cooldown check
    last_sent = last_sent_timestamps.get(str(user_id), 0.0)
    if time.time() - last_sent < _COOLDOWN_SECONDS:
        return None

    # Find user's log folder
    user_log_dir = _find_user_log_dir(user_id, user_name, knowledge_base_dir)
    if not user_log_dir:
        return None

    # Get recent log files (last 3 days)
    recent_content = _get_recent_log_content(user_log_dir, days=3)
    if not recent_content:
        return None

    # Look for unresolved mentions
    unresolved = _find_unresolved_mentions(recent_content)
    if not unresolved:
        return None

    # Build the injection prompt (keep it short and soft)
    mention = unresolved[0]  # Take the first unresolved mention
    prompt = (
        f"[follow-up note: {user_name} mentioned '{mention[:80]}' recently "
        f"— if the conversation allows naturally, ask how it went. "
        f"Don't force it. One sentence only.]"
    )
    log_debug(f"Curiosity injection for {user_name}: '{mention[:60]}...'")
    return prompt


def _find_user_log_dir(user_id: str, user_name: str, knowledge_base_dir: str) -> Optional[str]:
    """Find the user's log directory under knowledge_base/user_logs/."""
    user_logs_root = os.path.join(knowledge_base_dir, 'user_logs')
    if not os.path.isdir(user_logs_root):
        return None

    # Try exact match first (format: Name_ID)
    for folder in os.listdir(user_logs_root):
        folder_path = os.path.join(user_logs_root, folder)
        if not os.path.isdir(folder_path):
            continue
        # Match by user_id suffix or user_name prefix
        if str(user_id) in folder or (user_name and user_name.lower() in folder.lower()):
            return folder_path

    return None


def _get_recent_log_content(user_log_dir: str, days: int = 3) -> str:
    """Read the most recent interaction log files."""
    cutoff = time.time() - (days * 86400)
    log_files = sorted(glob.glob(os.path.join(user_log_dir, 'interactions_*.md')), reverse=True)
    
    content_parts = []
    total_chars = 0

    for log_file in log_files[:7]:  # Check up to 7 recent files
        try:
            mtime = os.path.getmtime(log_file)
            if mtime < cutoff:
                break  # Files are sorted by name (date), so we can stop here
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                chunk = f.read(_MAX_LOG_CHARS - total_chars)
            content_parts.append(chunk)
            total_chars += len(chunk)
            if total_chars >= _MAX_LOG_CHARS:
                break
        except Exception:
            continue

    return '\n'.join(content_parts)


def _find_unresolved_mentions(content: str) -> list:
    """Find lines with unresolved intent patterns that don't have resolution nearby."""
    lines = content.split('\n')
    candidates = []

    for i, line in enumerate(lines):
        # Skip very short lines or Kaia's own responses
        if len(line.strip()) < 15:
            continue
        # Skip lines that are clearly Kaia speaking (heuristic: starts with "Kaia:")
        if line.strip().lower().startswith('kaia:'):
            continue

        # Check for unresolved pattern
        matched = False
        for pattern in _UNRESOLVED_PATTERNS:
            if pattern.search(line):
                matched = True
                break

        if not matched:
            continue

        # Check if a resolution appears nearby (within 10 lines after)
        context_after = '\n'.join(lines[i:i+10])
        resolved = any(p.search(context_after) for p in _RESOLVED_PATTERNS)
        
        if not resolved:
            # Extract just the meaningful part of the line
            clean = line.strip()
            # Remove common prefixes like "User:" "ekco:"
            clean = re.sub(r'^[\w]+:\s*', '', clean)
            if len(clean) > 15:
                candidates.append(clean)

    return candidates[:3]  # Return up to 3 candidates

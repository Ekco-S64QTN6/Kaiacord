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
from utils.infrastructure.logging.kaia_logger import log_info

# Something the speaker said *they* would do. The subject has to be them:
# "blizzard is going to try", "keep working on that zen" and "was hoping to"
# matched when any subject would do, and were half of all hits.
_I = r"(?:i|we)"
_I_AM = r"(?:i'?m|i am|we'?re|we are)"
_UNRESOLVED_PATTERNS = [
    re.compile(rf"\b{_I}'?ll\s+(?:let you know|update you|check|test|try|look into|fix|get back)\b", re.IGNORECASE),
    # "going to fix it tonight" at the start of a sentence: the "i" dropped.
    re.compile(rf"(?:\b{_I_AM}\s+|(?:^|[.!?]\s+))(?:going to|gonna)\s+(?:try|check|fix|test|look into|work on|start|finish|build|run)\b", re.IGNORECASE),
    re.compile(rf"\b{_I}\s+will\s+(?:try|check|look|test|fix|update|work on)\b", re.IGNORECASE),
    re.compile(rf"\b{_I_AM}\s+(?:working on|planning to|hoping to)\b", re.IGNORECASE),
    re.compile(rf"\b{_I}\s+(?:plan|hope)\s+to\b", re.IGNORECASE),
    re.compile(r"\bget back to you\b", re.IGNORECASE),
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

    # Adaptive lookback: frequent users get 3 days, infrequent get 14
    last_file_mtime = _get_latest_log_mtime(user_log_dir)
    days_since_last = (time.time() - last_file_mtime) / 86400 if last_file_mtime else 999
    
    if days_since_last > 30:
        return None  # Too stale for curiosity
    elif days_since_last > 7:
        lookback_days = 14
    else:
        lookback_days = 3

    # Get recent log files
    recent_content = _get_recent_log_content(user_log_dir, days=lookback_days)
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
    log_info(f"🔍 Curiosity Scanner: injected unresolved mention '{mention[:60]}...' for {user_name}")
    return prompt


def _find_user_log_dir(user_id: str, user_name: str, knowledge_base_dir: str) -> Optional[str]:
    """The user's Discord log folder, `<Name>_<id>` under knowledge_base/user_logs/.

    By id first. A name match used to win on directory order, so Ekco's turns
    were scanned from `forum_Ekco_251675` — his forum history, not his chat.
    `forum_` folders are never a Discord user's.
    """
    user_logs_root = os.path.join(knowledge_base_dir, 'user_logs')
    if not os.path.isdir(user_logs_root):
        return None

    folders = [f for f in os.listdir(user_logs_root)
               if not f.startswith(('forum_', '.', '_'))
               and os.path.isdir(os.path.join(user_logs_root, f))]
    uid = str(user_id)
    for folder in folders:
        if folder.endswith(f"_{uid}"):
            return os.path.join(user_logs_root, folder)
    if user_name:
        prefix = f"{user_name.lower()}_"
        for folder in folders:
            if folder.lower().startswith(prefix):
                return os.path.join(user_logs_root, folder)
    return None


def _get_latest_log_mtime(user_log_dir: str) -> Optional[float]:
    """Get the mtime of the most recent log file."""
    log_files = glob.glob(os.path.join(user_log_dir, 'interactions_*.md'))
    if not log_files:
        return None
    try:
        return max(os.path.getmtime(f) for f in log_files)
    except Exception:
        return None


def _get_recent_log_content(user_log_dir: str, days: int = 3) -> str:
    """The most recent `_MAX_LOG_CHARS` of the interaction logs, oldest first.

    Reads from the end of each day's file: the head of the newest file is the
    start of today, which is the part least likely to still be open.
    """
    cutoff = time.time() - (days * 86400)
    log_files = sorted(glob.glob(os.path.join(user_log_dir, 'interactions_*.md')), reverse=True)

    content_parts = []
    total_chars = 0

    for log_file in log_files[:7]:  # Check up to 7 recent files
        try:
            if os.path.getmtime(log_file) < cutoff:
                break  # Files are sorted by name (date), so we can stop here
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except OSError:
            continue
        chunk = text[-(_MAX_LOG_CHARS - total_chars):]
        content_parts.append(chunk)
        total_chars += len(chunk)
        if total_chars >= _MAX_LOG_CHARS:
            break

    return '\n'.join(reversed(content_parts))


# "[2026-09-22 03:09:07] Ekco: text" — a line without this prefix continues the
# previous speaker's turn. Older logs also put a reply on the same line as the
# message it answered, so every such marker starts a new segment.
_TURN = re.compile(r"^\[[^\]]+\]\s+([^:]{1,60}):\s*(.*)$", re.S)
_INLINE_TURN = re.compile(r"(?=\[\d{4}-\d\d-\d\d \d\d:\d\d(?::\d\d)?\] )")


def _segments(content: str) -> list:
    """Log lines, split so that each turn marker starts its own segment."""
    out = []
    for line in content.split('\n'):
        out.extend(p for p in _INLINE_TURN.split(line) if p != '' or not line)
    return out


def _user_lines(segments: list):
    """(index, text) of every segment the user wrote; Kaia's turns are skipped."""
    speaker = None
    in_frontmatter = False
    for i, seg in enumerate(segments):
        stripped = seg.strip()
        if stripped == '---':
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        m = _TURN.match(stripped)
        if m:
            speaker, stripped = m.group(1).strip().lower(), m.group(2).strip()
        if speaker and speaker != 'kaia':
            yield i, stripped


def _find_unresolved_mentions(content: str) -> list:
    """The user's own lines with unresolved intent and no resolution soon after."""
    segments = _segments(content)
    candidates = []

    for i, line in _user_lines(segments):
        if len(line) < 15:
            continue
        if not any(p.search(line) for p in _UNRESOLVED_PATTERNS):
            continue

        # Check if a resolution appears nearby (within 10 segments after)
        context_after = '\n'.join(segments[i:i+10])
        if any(p.search(context_after) for p in _RESOLVED_PATTERNS):
            continue
        candidates.append(line)

    # Most recent first: the prompt takes the first one.
    return candidates[::-1][:3]

"""
Proactive Conversation Initiation
==================================

Kaia occasionally speaks first — triggered by knowledge ingestion, user
absence, dream insights, personal memories, mood reflections, or belief
musings. Heavily rate-limited to avoid annoyance.

Guardrails:
- Maximum 2 proactive messages per 24-hour period globally
- Only post in channels where Kaia has recently been active
- Time gate: only between 9 AM – 10 PM local time
- Minimum 4 hours between proactive messages
- Natural, casual openers — never pushy
- Topic diversity: no same source type twice in a row,
  no source type more than 3× in last 10 messages
"""

import asyncio
import json
import os
import time
import uuid
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from utils.infrastructure.logging.kaia_logger import (
    log_debug, log_info, log_warning, log_success,
)

# ── Rate Limiting Constants ─────────────────────────────────────────
MAX_DAILY_PROACTIVE = 2
MIN_INTERVAL_SECONDS = 4 * 3600  # 4 hours between proactive messages
QUIET_HOUR_START = 9   # 9 AM
QUIET_HOUR_END = 22    # 10 PM
ABSENCE_THRESHOLD_DAYS = 3  # User must be gone this long to trigger

# ── Diversity Constants ─────────────────────────────────────────────
DIVERSITY_LOG_PATH = os.path.join("memory", "proactive_topics.json")
MAX_DIVERSITY_HISTORY = 10
MAX_SAME_SOURCE_IN_WINDOW = 3  # No source type more than 3× in last 10

# ── Source Weights ──────────────────────────────────────────────────
# Higher weight = more likely to be selected.
# Conversation-grounded sources are heavily favored over generic ones
# to avoid cookie-cutter "AI social media post" vibes.
SOURCE_WEIGHTS = {
    "conversation_followup": 35,  # Follow-up on recent channel conversations
    "personal_memory": 25,       # Callback to specific user interactions
    "overheard": 20,             # Reaction to overheard conversation themes
    "belief_musing": 15,         # Musing on a formed belief
    "anchor_callback": 15,       # Episodic memory callback
    "dream_echo": 10,            # Growth event / belief revision echo
    "knowledge": 8,              # Recent ingestion reference (deprioritized)
    "mood_reflection": 8,        # Mood-driven idle thought (deprioritized)
    "idle_quirk": 3,             # Random spontaneous thought (rare)
}


def build_digest_content_id(timestamp) -> str:
    """Stable dedup key for an observation-digest entry.

    Shared by the proactive engine and the digest broadcast in
    background_tasks so both write and check the same identifier.
    """
    try:
        return f"obs_digest:{float(timestamp):.0f}"
    except (TypeError, ValueError):
        return ""


def mark_digest_broadcast(content_id: str) -> None:
    """Flag the observation-digest entry behind `content_id` as aired.

    Best-effort and atomic: the diversity log is still the authoritative
    dedup record, this just makes the digest file self-describing.
    """
    if not content_id or not content_id.startswith("obs_digest:"):
        return
    try:
        digest_path = os.path.join("memory", "observation_digest.json")
        if not os.path.exists(digest_path):
            return
        with open(digest_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        changed = False
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if build_digest_content_id(entry.get("timestamp", 0)) == content_id:
                if not entry.get("broadcast"):
                    entry["broadcast"] = True
                    changed = True
                break
        if not changed:
            return
        tmp = digest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
        os.replace(tmp, digest_path)
    except Exception as e:
        log_debug(f"Marking digest as broadcast failed (non-fatal): {e}")


@dataclass
class ProactiveTrigger:
    """A resolved trigger that should produce a proactive message."""
    trigger_type: str  # "absence", "knowledge", "dream_echo", etc.
    channel_id: int
    context: str       # Brief context for the LLM prompt
    target_user: Optional[str] = None  # Display name, if user-specific
    source_category: str = ""  # For diversity tracking
    content_id: str = ""  # Specific content identifier for dedup (e.g. filename)


class ProactiveEngine:
    """Evaluates trigger conditions and generates proactive conversation starters."""

    def __init__(self):
        self._last_trigger_type: Optional[str] = None

    # ── Time & Rate Checks ──────────────────────────────────────────

    def _is_within_hours(self) -> bool:
        """Check if current time is within the allowed proactive window."""
        hour = datetime.now().hour
        return QUIET_HOUR_START <= hour < QUIET_HOUR_END

    def is_within_hours(self) -> bool:
        """Public alias so out-of-band senders (e.g. the observation digest
        broadcast) honour the same quiet-hours window as the proactive loop."""
        return self._is_within_hours()

    def was_content_broadcast(self, content_id: str) -> bool:
        """True if a proactive message carrying this content_id was already sent.

        The diversity log is the single source of truth for what has actually
        reached chat, so both the random proactive path and the direct
        observation-digest broadcast can dedupe against the same record.
        """
        if not content_id:
            return False
        try:
            return any(
                h.get("content_id") == content_id
                for h in self._load_diversity_log()
            )
        except Exception:
            return False

    def _is_rate_limited(self, bot_state) -> bool:
        """Check if we've exceeded daily or interval limits."""
        now = time.time()
        today = datetime.now().strftime('%Y-%m-%d')

        # Reset daily count if new day
        last_date = getattr(bot_state, 'last_proactive_date', '')
        if last_date != today:
            bot_state.proactive_daily_count = 0
            bot_state.last_proactive_date = today

        # Daily cap
        if getattr(bot_state, 'proactive_daily_count', 0) >= MAX_DAILY_PROACTIVE:
            return True

        # Minimum interval
        last_sent = getattr(bot_state, 'proactive_last_sent', 0.0)
        if now - last_sent < MIN_INTERVAL_SECONDS:
            return True

        return False

    def _find_active_channel(self, bot_state) -> Optional[int]:
        """Find the most recently active channel where Kaia has spoken."""
        if not bot_state.channel_last_activity:
            return None

        now = time.time()
        candidates = [
            (ch_id, ts) for ch_id, ts in bot_state.channel_last_activity.items()
            if now - ts < 86400  # Active in last 24h
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    # ── Diversity Log ───────────────────────────────────────────────

    def _load_diversity_log(self) -> list:
        """Load the proactive topic diversity history."""
        try:
            if os.path.exists(DIVERSITY_LOG_PATH):
                with open(DIVERSITY_LOG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('history', [])
        except Exception:
            pass
        return []

    def _save_diversity_log(self, history: list) -> None:
        """Atomically save the diversity log."""
        try:
            os.makedirs(os.path.dirname(DIVERSITY_LOG_PATH), exist_ok=True)
            tmp = DIVERSITY_LOG_PATH + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({"history": history[-MAX_DIVERSITY_HISTORY:]}, f, indent=2)
            os.replace(tmp, DIVERSITY_LOG_PATH)
        except Exception as e:
            log_debug(f"Diversity log save failed (non-fatal): {e}")

    def _is_source_allowed(self, source_type: str, history: list) -> bool:
        """Check if a source type passes diversity constraints."""
        if not history:
            return True

        # No same source twice in a row
        if history[-1].get('source') == source_type:
            return False

        # No source more than MAX_SAME_SOURCE_IN_WINDOW times in window
        recent_sources = [h.get('source') for h in history[-MAX_DIVERSITY_HISTORY:]]
        if recent_sources.count(source_type) >= MAX_SAME_SOURCE_IN_WINDOW:
            return False

        return True

    # ── Source Gathering ────────────────────────────────────────────

    def _check_absence(self, bot_state) -> Optional[ProactiveTrigger]:
        """Check if any familiar user has been absent long enough."""
        try:
            now = time.time()
            channel_id = self._find_active_channel(bot_state)
            if not channel_id:
                return None

            for user_id, rel in bot_state.relationships.items():
                count = rel.get('interaction_count', 0)
                last_seen = rel.get('last_seen', 0)
                if count >= 25 and last_seen > 0:
                    days_absent = (now - last_seen) / 86400
                    if days_absent >= ABSENCE_THRESHOLD_DAYS:
                        last_proactive_for = rel.get('last_proactive_checkin', 0)
                        if now - last_proactive_for > 7 * 86400:
                            user_name = rel.get('display_name') or f'user {user_id[-4:]}'
                            return ProactiveTrigger(
                                trigger_type="absence",
                                channel_id=channel_id,
                                context=(
                                    f"{user_name} hasn't been around for "
                                    f"{int(days_absent)} days. You've had "
                                    f"{count} conversations with them."
                                ),
                                target_user=user_name,
                                source_category="absence",
                            )
        except Exception as e:
            log_debug(f"Absence trigger check failed (non-fatal): {e}")
        return None

    def _get_personal_memory(self) -> Optional[Tuple[str, str]]:
        """Pull a snippet from a recent user interaction log, biased toward
        more recent files.

        Returns (context_string, source_category) or None.
        """
        try:
            user_logs_dir = Path("knowledge_base") / "user_logs"
            if not user_logs_dir.exists():
                return None

            # Collect all interaction files from last 30 days
            now = time.time()
            cutoff = now - (30 * 86400)
            candidates = []
            for user_dir in user_logs_dir.iterdir():
                if not user_dir.is_dir() or user_dir.name.startswith('.'):
                    continue
                # Skip social/bluesky log dirs
                if user_dir.name.startswith('social_'):
                    continue
                for log_file in user_dir.glob("interactions_*.md"):
                    try:
                        mtime = log_file.stat().st_mtime
                        if mtime > cutoff:
                            candidates.append((log_file, user_dir.name, mtime))
                    except Exception:
                        continue

            if not candidates:
                return None

            # Recency-weighted selection: newer files get higher weight
            # Weight = days_fresh (1-30), so a file from today gets ~30x
            # the weight of one from 30 days ago
            weights = []
            for _, _, mtime in candidates:
                days_old = max(0.5, (now - mtime) / 86400)
                weights.append(31.0 - min(30.0, days_old))

            # Weighted random pick
            total_w = sum(weights)
            pick = secrets.randbelow(int(total_w * 100)) / 100.0
            cumulative = 0.0
            chosen_idx = len(candidates) - 1
            for i, w in enumerate(weights):
                cumulative += w
                if pick < cumulative:
                    chosen_idx = i
                    break

            log_file, user_dir_name, _ = candidates[chosen_idx]
            # Extract display name from directory name (format: Name_ID)
            display_name = user_dir_name.rsplit('_', 1)[0] if '_' in user_dir_name else user_dir_name

            # Read and find a substantive exchange
            text = log_file.read_text(encoding='utf-8', errors='ignore')
            lines = [
                ln for ln in text.splitlines()
                if ln.startswith('[') and '] ' in ln and len(ln) > 40
                and 'Kaia:' not in ln[:60]  # User lines, not Kaia's
            ]

            if not lines:
                return None

            # Pick a random substantive line
            line = secrets.choice(lines)
            # Strip timestamp prefix
            if '] ' in line:
                content = line.split('] ', 1)[1]
            else:
                content = line

            context = (
                f"You're thinking about a past conversation with {display_name}. "
                f"They said: \"{content[:200]}\". "
                f"Mention it casually, like it just crossed your mind."
            )
            return (context, "personal_memory", "", display_name)
        except Exception as e:
            log_debug(f"Personal memory source failed (non-fatal): {e}")
        return None

    def _get_belief_musing(self) -> Optional[Tuple[str, str]]:
        """Pick a random belief from beliefs.json for idle musing."""
        try:
            beliefs_path = Path("memory") / "beliefs.json"
            if not beliefs_path.exists():
                return None

            with open(beliefs_path, 'r', encoding='utf-8') as f:
                beliefs = json.load(f)

            if not beliefs:
                return None

            belief = secrets.choice(beliefs)
            topic = belief.get('topic', '')
            position = belief.get('position', '')

            if not topic or not position:
                return None

            context = (
                f"You've been thinking about your stance on '{topic}'. "
                f"Your current take: \"{position[:200]}\". "
                f"Share a thought about it like you've been mulling it over."
            )
            return (context, "belief_musing")
        except Exception as e:
            log_debug(f"Belief musing source failed (non-fatal): {e}")
        return None

    def _get_mood_reflection(self) -> Optional[Tuple[str, str]]:
        """Generate a mood-appropriate idle thought based on emotional state."""
        try:
            from utils.core.kaia_mood import emotional_arc
            v = emotional_arc.valence
            a = emotional_arc.arousal
            e = emotional_arc.social_energy

            # Build a mood-specific topic suggestion
            if v > 0.5 and e > 0.6:
                context = (
                    "You're in a good mood and feeling social. "
                    "Share something positive — a thought about something "
                    "you've enjoyed recently, or something you're looking forward to. "
                    "Keep it warm and genuine."
                )
            elif v > 0.15 and a < 0.35:
                context = (
                    "You're feeling calm and reflective. "
                    "Share a quiet observation — something you noticed, "
                    "a pattern you've been seeing, or a small realization. "
                    "Keep it thoughtful and low-key."
                )
            elif v < -0.15:
                context = (
                    "You're in a subdued mood. "
                    "Share something honest — maybe a frustration, "
                    "something that's been bugging you, or a question "
                    "you don't have an answer to. Keep it real."
                )
            elif e < 0.3:
                context = (
                    "You're socially drained but still present. "
                    "Drop a brief, low-energy observation. "
                    "Something dry, maybe a little wry. One sentence max."
                )
            else:
                context = (
                    "You're in a neutral, engaged state. "
                    "Share whatever's on your mind — "
                    "a random thought, a question, an idle wonder. "
                    "Let it be spontaneous."
                )

            return (context, "mood_reflection")
        except Exception as e:
            log_debug(f"Mood reflection source failed (non-fatal): {e}")
        return None

    def _get_knowledge_source(self, bot_state) -> Optional[Tuple[str, str]]:
        """Pull from recent ingestions with snippet context.

        Tracks used filenames in diversity log to avoid repeating
        the same ingestion.
        """
        try:
            recent = getattr(bot_state, 'recent_ingestions', [])
            if not recent:
                return None

            # Check diversity log for previously used ingestion filenames
            history = self._load_diversity_log()
            used_files = set()
            for h in history:
                cid = h.get('content_id', '')
                if cid:
                    used_files.add(cid)

            # Filter to entries not yet used
            available = []
            for entry in recent:
                if isinstance(entry, dict):
                    fn = entry.get('filename', '')
                else:
                    fn = str(entry)
                if fn and fn not in used_files:
                    available.append(entry)

            # If all have been used, allow any (cycle reset)
            if not available:
                available = list(recent)

            entry = secrets.choice(available)
            if isinstance(entry, dict):
                filename = entry.get('filename', str(entry))
                snippet = entry.get('snippet', '')[:300]
            else:
                filename = str(entry)
                snippet = ''

            # Clean up filename for display
            display_name = filename.replace('_', ' ').replace('.md', '')
            # Strip dream prefix clutter
            if display_name.startswith('dream '):
                parts = display_name.split(' ', 3)
                display_name = parts[-1] if len(parts) > 3 else display_name

            context = (
                f"You recently read something related to: '{display_name}'. "
            )
            if snippet:
                context += f"A fragment: \"{snippet[:200]}\". "
            context += (
                "Mention one interesting angle casually. "
                "Connect it to something relatable — "
                "don't just summarize technical details."
            )
            # Store filename as content_id for dedup tracking
            return (context, "knowledge", filename)
        except Exception as e:
            log_debug(f"Knowledge source failed (non-fatal): {e}")
        return None

    def _get_dream_echo(self) -> Optional[Tuple[str, str]]:
        """Pull a recent growth event (any type) for dream-inspired musing."""
        try:
            growth_path = Path("memory") / "growth_log.jsonl"
            if not growth_path.exists():
                return None

            size = growth_path.stat().st_size
            if size == 0:
                return None

            with open(growth_path, 'r', encoding='utf-8') as f:
                f.seek(max(0, size - 4000))
                tail = f.read()

            lines = tail.strip().splitlines()
            recent_events = []
            now = time.time()

            for line in reversed(lines[-15:]):
                try:
                    evt = json.loads(line)
                    age = now - evt.get('ts', 0)
                    if age < 7 * 86400:  # Within last 7 days
                        recent_events.append(evt)
                except Exception:
                    continue

            if not recent_events:
                return None

            evt = secrets.choice(recent_events)
            evt_type = evt.get('type', '')

            if evt_type == 'belief_revised':
                topic = evt.get('topic', 'something')
                new_pos = evt.get('new_position', '')[:150]
                context = (
                    f"You recently changed your mind about '{topic}'. "
                    f"Your new take: \"{new_pos}\". "
                    f"Mention it like you've been mulling it over."
                )
            elif evt_type == 'belief_formed':
                topic = evt.get('topic', 'something')
                position = evt.get('position', '')[:150]
                context = (
                    f"You've been forming a view on '{topic}': \"{position}\". "
                    f"Share the thought naturally, like it just crystallized."
                )
            elif evt_type == 'relationship_insight':
                user = evt.get('user', 'someone')
                summary = evt.get('summary', '')[:150]
                context = (
                    f"You had a realization about your dynamic with {user}: "
                    f"\"{summary}\". Mention it indirectly — "
                    f"don't name them unless it's natural."
                )
            elif evt_type == 'identity_shift':
                content = evt.get('content', '')[:200]
                context = (
                    f"You've noticed something shifting in how you see things: "
                    f"\"{content}\". Share the shift, not the meta-awareness."
                )
            else:
                return None

            return (context, "dream_echo")
        except Exception as e:
            log_debug(f"Dream echo source failed (non-fatal): {e}")
        return None

    def _get_anchor_callback(self) -> Optional[Tuple[str, str]]:
        """Pick a random episodic memory anchor for a callback."""
        try:
            anchors_path = Path("memory") / "anchors.json"
            if not anchors_path.exists():
                return None

            with open(anchors_path, 'r', encoding='utf-8') as f:
                anchors = json.load(f)

            if not anchors:
                return None

            anchor = secrets.choice(anchors)
            theme = anchor.get('theme', '')
            text = anchor.get('anchor_text', '')
            user_name = anchor.get('user_name')

            if not theme or not text:
                return None

            if user_name:
                context = (
                    f"You're remembering something about {user_name} and '{theme}': "
                    f"\"{text[:200]}\". Bring it up naturally."
                )
            else:
                context = (
                    f"A memory about '{theme}' surfaced: \"{text[:200]}\". "
                    f"Share the thought like it just came back to you."
                )
            return (context, "anchor_callback", "", user_name)
        except Exception as e:
            log_debug(f"Anchor callback source failed (non-fatal): {e}")
        return None

    def _get_idle_quirk(self) -> Optional[Tuple[str, str]]:
        """Occasionally produce a spontaneous, slightly off-kilter thought.

        Low weight (5) — fires rarely but adds lifelikeness. These are
        the kinds of random thoughts a person has while idle.
        """
        try:
            quirk_prompts = [
                (
                    "You just had a completely random thought — something "
                    "mundane, weird, or mildly philosophical. Not about tech. "
                    "Maybe about food, weather, an old memory, a hypothetical, "
                    "or something you noticed. Share it like you're thinking "
                    "out loud to nobody in particular."
                ),
                (
                    "You're bored and your mind wandered somewhere strange. "
                    "Share a question nobody asked — something idle and "
                    "slightly absurd. The kind of thing you'd text a friend "
                    "at 2am."
                ),
                (
                    "You just realized something obvious that you somehow "
                    "never thought about before. It's not profound — it's "
                    "the kind of 'wait, huh' moment everyone has. Share it."
                ),
            ]
            return (secrets.choice(quirk_prompts), "idle_quirk")
        except Exception as e:
            log_debug(f"Idle quirk source failed (non-fatal): {e}")
        return None

    # Digests older than this are no longer worth reacting to out loud —
    # the conversation they summarise has moved on.
    OVERHEARD_MAX_AGE_SECONDS = 6 * 3600

    def _get_overheard_digest(self) -> Optional[Tuple[str, str, str]]:
        """Retrieve the newest un-broadcast passive observation digest (P54-16).

        Walks newest-first and returns the first digest that is both fresh and
        has not already reached chat. Without the dedup the engine re-offered
        history[-1] on every evaluation, so a single digest could be aired
        several times while newer ones were never spoken.
        """
        try:
            from pathlib import Path
            import json
            digest_path = Path("memory/observation_digest.json")
            if not digest_path.exists():
                return None

            with open(digest_path, "r", encoding="utf-8") as f:
                history = json.load(f)

            if not history:
                return None

            now = time.time()
            for entry in reversed(history):
                if not isinstance(entry, dict):
                    continue
                digest_text = (entry.get("theme_digest") or "").strip()
                if not digest_text:
                    continue
                ts = entry.get("timestamp", 0)
                if ts and now - ts > self.OVERHEARD_MAX_AGE_SECONDS:
                    break  # older entries are only staler
                content_id = build_digest_content_id(ts)
                if entry.get("broadcast") or self.was_content_broadcast(content_id):
                    continue

                context = (
                    f"You overheard some conversation recently: '{digest_text}'. "
                    "Share your thoughts, comments, or reaction to this topic in the chat. "
                    "Keep it dry, slightly sardonic, and brief."
                )
                return (context, "overheard", content_id)
        except Exception as e:
            log_debug(f"Overheard digest source failed (non-fatal): {e}")
        return None

    def _get_conversation_followup(self, bot_state) -> Optional[Tuple[str, str]]:
        """Pick up a substantive thread from recent channel conversations.

        Scans channel_memory for meaty user messages (>60 chars) from the
        last 48 hours and generates a follow-up prompt grounded in what
        was actually discussed. This is the primary source for making
        proactive posts feel human and contextually relevant.
        """
        try:
            if not bot_state or not bot_state.channel_memory:
                return None

            now = time.time()
            cutoff = now - (48 * 3600)  # Last 48 hours

            # Collect substantive user messages across all channels
            substantive_msgs = []
            for ch_id, mem in bot_state.channel_memory.items():
                for msg in mem:
                    if msg.get('role') != 'user':
                        continue
                    ts = msg.get('timestamp', 0)
                    if ts < cutoff:
                        continue
                    content = msg.get('content', '')
                    # Skip very short messages (reactions, links, emojis)
                    if len(content) < 60:
                        continue
                    # Extract author name from "Author: message" format
                    author = ''
                    if ':' in content:
                        author = content.split(':', 1)[0].strip()
                        content = content.split(':', 1)[1].strip()
                    # Skip Kaia-Autonomous channel logs
                    if author.lower().startswith('kaia'):
                        continue
                    substantive_msgs.append({
                        'author': author,
                        'content': content[:300],
                        'ts': ts,
                        'channel_id': ch_id,
                    })

            if not substantive_msgs:
                return None

            # Bias toward more recent messages
            # Weight = hours_fresh (1-48), so a message from 1h ago gets ~48x
            weights = []
            for msg in substantive_msgs:
                hours_old = max(0.5, (now - msg['ts']) / 3600)
                weights.append(49.0 - min(48.0, hours_old))

            total_w = sum(weights)
            if total_w <= 0:
                return None

            pick = secrets.randbelow(int(total_w * 100)) / 100.0
            cumulative = 0.0
            chosen = substantive_msgs[-1]
            for i, w in enumerate(weights):
                cumulative += w
                if pick < cumulative:
                    chosen = substantive_msgs[i]
                    break

            author = chosen['author'] or 'someone'
            content_snippet = chosen['content'][:200]

            # Build a context that grounds the proactive post in real conversation
            context = (
                f"You've been thinking about something {author} said recently: "
                f"\"{content_snippet}\". "
                f"You want to add a thought, a question, or a follow-up "
                f"observation about it. Don't repeat what they said — "
                f"build on it or take it somewhere new."
            )
            return (context, "conversation_followup", "", author)
        except Exception as e:
            log_debug(f"Conversation followup source failed (non-fatal): {e}")
        return None

    # ── Source Selection ────────────────────────────────────────────

    def _gather_candidate_sources(
        self, bot_state,
    ) -> List[Tuple[str, int, str, str, Optional[str]]]:
        """Collect all viable proactive sources with their weights.

        Returns list of (source_type, weight, context_string, content_id, target_user) tuples.
        """
        candidates = []

        # Each source function returns (context, category) or None
        source_fns = [
            ("conversation_followup", lambda: self._get_conversation_followup(bot_state)),
            ("personal_memory", self._get_personal_memory),
            ("belief_musing", self._get_belief_musing),
            ("mood_reflection", self._get_mood_reflection),
            ("knowledge", lambda: self._get_knowledge_source(bot_state)),
            ("dream_echo", self._get_dream_echo),
            ("anchor_callback", self._get_anchor_callback),
            ("idle_quirk", self._get_idle_quirk),
            ("overheard", self._get_overheard_digest),
        ]

        for source_type, fn in source_fns:
            try:
                result = fn()
                if result:
                    content_id = ""
                    target_user = None
                    # Unpack based on length dynamically
                    if len(result) == 4:
                        context, category, content_id, target_user = result
                    elif len(result) == 3:
                        context, category, content_id = result
                    else:
                        context, category = result
                    weight = SOURCE_WEIGHTS.get(source_type, 10)
                    candidates.append((source_type, weight, context, content_id, target_user))
            except Exception:
                continue

        return candidates

    def _select_diverse_source(
        self, candidates: List[Tuple[str, int, str, str, Optional[str]]]
    ) -> Optional[Tuple[str, str, str, Optional[str]]]:
        """Pick a source using weighted random, filtered by diversity history.

        Returns (source_type, context_string, content_id, target_user) or None.
        """
        if not candidates:
            return None

        history = self._load_diversity_log()

        # Filter candidates by diversity constraints
        allowed = [
            (stype, weight, ctx, cid, tuser) for stype, weight, ctx, cid, tuser in candidates
            if self._is_source_allowed(stype, history)
        ]

        # If diversity filter blocks everything, relax to just
        # "no same source twice in a row"
        if not allowed:
            last_source = history[-1].get('source', '') if history else ''
            allowed = [
                (stype, weight, ctx, cid, tuser)
                for stype, weight, ctx, cid, tuser in candidates
                if stype != last_source
            ]

        # If still nothing, allow anything
        if not allowed:
            allowed = candidates

        # Weighted random selection
        total_weight = sum(w for _, w, _, _, _ in allowed)
        if total_weight <= 0:
            return None

        pick = secrets.randbelow(total_weight)
        cumulative = 0
        for stype, weight, ctx, cid, tuser in allowed:
            cumulative += weight
            if pick < cumulative:
                return (stype, ctx, cid, tuser)

        # Fallback (shouldn't reach here)
        stype, _, ctx, cid, tuser = allowed[-1]
        return (stype, ctx, cid, tuser)

    # ── Main Trigger Evaluation ─────────────────────────────────────

    async def evaluate_triggers(
        self,
        bot_state,
        dream_engine=None,
    ) -> Optional[ProactiveTrigger]:
        """Evaluate all trigger conditions and return the best one, or None.

        Called by background_tasks every ~30 minutes.
        """
        if not self._is_within_hours():
            return None

        if self._is_rate_limited(bot_state):
            return None

        channel_id = self._find_active_channel(bot_state)
        if not channel_id:
            return None

        # ── Priority 1: User Absence (always wins if applicable) ────
        absence_trigger = self._check_absence(bot_state)
        if absence_trigger:
            absence_trigger.channel_id = channel_id
            return absence_trigger

        # ── Weighted Source Selection ───────────────────────────────
        candidates = self._gather_candidate_sources(bot_state)

        if not candidates:
            return None

        selection = self._select_diverse_source(candidates)
        if not selection:
            return None

        source_type, context, content_id, target_user = selection

        return ProactiveTrigger(
            trigger_type=source_type,
            channel_id=channel_id,
            context=context,
            source_category=source_type,
            content_id=content_id,
            target_user=target_user,
        )

    # ── Message Generation ──────────────────────────────────────────

    def _gather_cognitive_injections(
        self,
        trigger: ProactiveTrigger,
        bot_state,
    ) -> str:
        """Gather a lightweight subset of cognitive injections for the
        proactive system prompt.

        Mirrors the most impactful features from message_processor's
        28-feature pipeline without overwhelming the short-form output.
        Each injection is wrapped in try/except to ensure non-critical
        features never prevent message generation.
        """
        injections: List[str] = []

        # 1. Emotional Arc — persistent mood vector
        try:
            from utils.core.kaia_mood import emotional_arc
            arc_line = emotional_arc.get_prompt_injection()
            if arc_line:
                injections.append(arc_line)
        except Exception:
            pass

        # 2. Channel Memory Context — what was recently discussed
        try:
            if bot_state and trigger.channel_id:
                channel_mem = bot_state.channel_memory.get(trigger.channel_id)
                if channel_mem:
                    recent = list(channel_mem)[-8:]
                    if recent:
                        lines = []
                        for msg in recent:
                            role = msg.get('role', '')
                            content = msg.get('content', '')[:200]
                            if role == 'assistant':
                                lines.append(f"  Kaia: {content}")
                            elif role == 'user':
                                lines.append(f"  {content}")
                            elif role == 'system' and '[summary' in content.lower():
                                lines.append(f"  {content[:150]}")
                        if lines:
                            injections.append(
                                "[recent conversation in this channel:\n"
                                + "\n".join(lines)
                                + "\n]"
                            )
        except Exception:
            pass

        # 3. Relationship Stage — familiarity with target user
        try:
            if bot_state and trigger.target_user:
                # Find the user_id for the target user
                for user_id, rel in bot_state.relationships.items():
                    name = rel.get('display_name', '')
                    if name and (
                        trigger.target_user.lower() in name.lower()
                        or name.lower() in trigger.target_user.lower()
                    ):
                        stage_line = bot_state.get_stage_injection(
                            int(user_id), trigger.target_user
                        )
                        if stage_line:
                            injections.append(stage_line)
                        break
        except Exception:
            pass

        # 4. Beliefs — topically relevant persistent opinions
        try:
            beliefs_path = os.path.join("memory", "beliefs.json")
            if os.path.exists(beliefs_path):
                with open(beliefs_path, 'r', encoding='utf-8') as bf:
                    all_beliefs = json.load(bf)
                if all_beliefs and trigger.context:
                    ctx_lower = trigger.context.lower()
                    ctx_words = set(ctx_lower.split())
                    stop_words = {
                        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'you',
                        'i', 'to', 'of', 'in', 'for', 'on', 'with', 'and',
                        'or', 'but', 'not', 'about', 'just', 'like', 'your',
                    }
                    ctx_words -= stop_words
                    matched = []
                    for b in all_beliefs:
                        topic = b.get('topic', '').lower()
                        topic_words = set(topic.split()) - stop_words
                        if ctx_words & topic_words:
                            matched.append(
                                f"{b['topic']}: {b.get('position', '')[:100]}"
                            )
                        elif len(topic) > 4 and topic in ctx_lower:
                            matched.append(
                                f"{b['topic']}: {b.get('position', '')[:100]}"
                            )
                        if len(matched) >= 2:
                            break
                    if matched:
                        injections.append(
                            f"[your current stances: {'; '.join(matched)}]"
                        )
        except Exception:
            pass

        # 5. Identity Stream — recent self-reflection
        try:
            identity_path = os.path.join("memory", "identity_stream.md")
            if os.path.exists(identity_path):
                with open(identity_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    snippet = content[-400:]
                    # Find a clean sentence start
                    period_idx = snippet.find('. ')
                    if period_idx > 0 and period_idx < 100:
                        snippet = snippet[period_idx + 2:]
                    injections.append(
                        f"[recent self-reflection: {snippet.strip()}]"
                    )
        except Exception:
            pass

        # 6. Inner Monologue — if available via ctx
        try:
            if bot_state:
                monologue = getattr(bot_state, '_monologue_ref', None)
                if monologue:
                    mono_text = monologue.get_injection()
                    if mono_text:
                        injections.append(mono_text)
        except Exception:
            pass

        return "\n\n".join(injections)

    async def generate_opener(
        self,
        trigger: ProactiveTrigger,
        ollama_client,
        chat_model: str,
        persona: str,
        bot_state=None,
    ) -> Optional[str]:
        """Generate a natural conversation opener from a trigger.

        Uses a system/user message split with selective cognitive
        injections mirroring the main chat pipeline's most impactful
        features (channel memory, relationship, beliefs, identity
        stream, emotional arc).

        Returns the message text, or None on failure.
        """
        # Get current mood context
        mood_desc = ""
        try:
            from utils.core.kaia_mood import emotional_arc
            mood_desc = emotional_arc.get_prompt_injection()
        except Exception:
            pass

        # Time-of-day flavor
        hour = datetime.now().hour
        if hour < 12:
            time_flavor = "it's morning"
        elif hour < 17:
            time_flavor = "it's afternoon"
        else:
            time_flavor = "it's evening"

        # Determine if the target user is the active conversational partner in target channel
        is_active_user = False
        active_user_name = None
        if bot_state and trigger.channel_id:
            channel_mem = bot_state.channel_memory.get(trigger.channel_id)
            if channel_mem:
                for msg in reversed(channel_mem):
                    if msg.get('role') == 'user':
                        content = msg.get('content', '')
                        if ':' in content:
                            active_user_name = content.split(':', 1)[0].strip()
                            break
        
        if active_user_name and trigger.target_user:
            if trigger.target_user.lower() in active_user_name.lower() or active_user_name.lower() in trigger.target_user.lower():
                is_active_user = True

        # Source-specific voice guidance
        voice_hints = {
            "conversation_followup": (
                f"Something from a recent conversation stuck with you. "
                f"You want to follow up on it — add a new angle, "
                f"ask a question, or share a related thought. "
                f"Don't rehash what was said. Build on it or take "
                f"it somewhere the conversation didn't go. "
                f"Example tone: 'been thinking about what "
                f"{trigger.target_user or 'you'} said about...'"
            ),
            "absence": (
                f"You haven't seen {trigger.target_user} in a while. "
                f"Generate a casual, low-key check-in. Not clingy — "
                f"just noticing they've been gone. "
                f"Example tone: 'hey {trigger.target_user}, been quiet "
                f"without you around. everything good?'"
            ),
            "personal_memory": (
                f"You're recalling something from a past conversation with {trigger.target_user}, "
                f"who is the person you are currently talking to. "
                f"Bring it up like it just crossed your mind, addressing them directly as 'you'. "
                f"Example tone: 'was just thinking about that thing you said about...'"
                if is_active_user else
                f"You're recalling something that {trigger.target_user} said in a past conversation. "
                f"Since you are speaking in a general channel where {trigger.target_user} is not the main "
                f"active participant, do NOT address the channel as 'you' or attribute the comment to them. "
                f"Instead, refer to {trigger.target_user} by name. "
                f"Example tone: 'was just thinking about that thing {trigger.target_user} said about...'"
            ) if trigger.target_user else (
                "You're recalling something from a past conversation. "
                "Bring it up like it just crossed your mind. "
                "Example tone: 'was just thinking about that thing you said about...'"
            ),
            "belief_musing": (
                "You've been reflecting on a topic and want to share "
                "where your thinking landed. Not announcing a thesis — "
                "just thinking out loud. "
                "Example tone: 'been sitting with this thought about...'"
            ),
            "mood_reflection": (
                "You're sharing what's on your mind right now based on "
                "how you're feeling. Keep it genuine and spontaneous. "
                "Example tone: 'kind of a [mood] day. anyone else...'"
            ),
            "knowledge": (
                "You read something and want to share one angle of it. "
                "Don't summarize — pick the part that stuck with you. "
                "Connect it to something human and relatable. "
                "Example tone: 'read something earlier that made me "
                "think about...'"
            ),
            "dream_echo": (
                "Something from a recent reflection resurfaced. Share it "
                "like a half-formed realization. "
                "Example tone: 'this has been rattling around in my head...'"
            ),
            "anchor_callback": (
                f"A memory just surfaced about {trigger.target_user} (who you are talking to now). "
                f"Bring it up casually, addressing them as 'you'. "
                f"Example tone: 'randomly remembered that conversation we had about...'"
                if is_active_user else
                f"A memory just surfaced about {trigger.target_user}. "
                f"Since they are not the active participant, refer to them by name. "
                f"Example tone: 'randomly remembered that conversation with {trigger.target_user} about...'"
            ) if trigger.target_user else (
                "A memory just surfaced — something someone said or "
                "something you noticed before. Bring it up casually. "
                "Example tone: 'randomly remembered that conversation "
                "about...'"
            ),
            "idle_quirk": (
                "You had a random thought and you're sharing it. "
                "Keep it spontaneous, maybe a little weird. "
                "Example tone: 'does anyone else ever think about...'"
            ),
        }

        instruction = voice_hints.get(
            trigger.trigger_type, "Share a thought naturally."
        )

        # ── Cognitive Injections (selective subset of main pipeline) ─
        cognitive_context = self._gather_cognitive_injections(
            trigger, bot_state
        )

        # ── System Prompt (persona + injections) ────────────────────
        system_prompt = persona
        if cognitive_context:
            system_prompt += f"\n\n{cognitive_context}"

        # ── User Prompt (situation + trigger + voice) ───────────────
        user_prompt = (
            f"SITUATION: You are starting an unprompted conversation. "
            f"Nobody asked you to speak — you just have something on "
            f"your mind.\n\n"
            f"TIME: {time_flavor}\n"
            f"{mood_desc}\n\n"
            f"CONTEXT: {trigger.context}\n\n"
            f"VOICE: {instruction}\n\n"
            f"Rules:\n"
            f"- 1-2 sentences max, lowercase, casual\n"
            f"- No roleplay asterisks, no headers, no markdown\n"
            f"- Sound like a person who just thought of something, "
            f"not a bot making an announcement\n"
            f"- Don't start with 'hey everyone' — be specific or direct\n"
            f"- You have broad interests — don't default to tech jargon "
            f"unless the topic is explicitly technical\n"
            f"- Be yourself: blunt, dry, grounded\n"
            f"- You MUST write in the first person ('i', 'my', 'me'). "
            f"Never refer to yourself or Kaia in the third person "
            f"('she', 'her').\n"
            f"Your message:"
        )

        try:
            from utils.infrastructure.gpu.gpu_manager import (
                gpu_memory_manager, GPUTaskPriority,
            )

            async def _run_proactive():
                return await ollama_client.chat(
                    model=chat_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options={
                        "temperature": 0.75,
                        "num_predict": 150,
                        "num_gpu": 99,
                        "num_ctx": 16384,
                    },
                    keep_alive=-1,
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(_run_proactive(), timeout=45.0),
                task_id=f"proactive_{uuid.uuid4().hex[:8]}",
            )

            raw = response["message"]["content"].strip()

            # Basic cleanup
            raw = raw.strip('"\'')
            if raw.startswith("Kaia:") or raw.startswith("kaia:"):
                raw = raw[5:].strip()

            # Full post-generation safety pipeline
            # 1. Contamination filter (hallucination/fabrication guard)
            try:
                from utils.core.response_filter import (
                    BotSpeakFilter, EmergencyContaminationFilter,
                )
                filtered = EmergencyContaminationFilter.filter_response(raw)
                if filtered is None:
                    log_warning(
                        "Proactive opener failed contamination filter. "
                        "Discarding."
                    )
                    return None
                raw = filtered
            except Exception:
                pass

            # 2. BotSpeak hardening (persona consistency)
            try:
                from utils.core.response_filter import BotSpeakFilter
                raw = BotSpeakFilter.harden(raw)
            except Exception:
                pass

            # 3. Style collapsers (ellipsis/em-dash drift)
            try:
                from utils.core.safety_pipeline import (
                    PostGenerationSafetyPipeline,
                )
                raw = PostGenerationSafetyPipeline.apply_style_collapsers(raw)
            except Exception:
                pass

            if raw and len(raw) > 10:
                log_info(
                    f"Proactive opener generated "
                    f"({trigger.source_category or trigger.trigger_type}): "
                    f"{raw[:80]}"
                )
                return raw

        except asyncio.TimeoutError:
            log_debug("Proactive generation timed out (non-fatal)")
        except Exception as e:
            log_warning(f"Proactive generation failed: {e}")

        return None

    # ── Post-Send Recording ─────────────────────────────────────────

    def record_sent(
        self, bot_state, trigger: ProactiveTrigger, message: str = ""
    ) -> None:
        """Record that a proactive message was sent, updating cooldowns
        and diversity log."""
        now = time.time()
        bot_state.proactive_last_sent = now
        bot_state.proactive_daily_count = (
            getattr(bot_state, 'proactive_daily_count', 0) + 1
        )
        bot_state.last_proactive_date = datetime.now().strftime('%Y-%m-%d')

        # For absence triggers, record per-user to avoid spamming
        if trigger.trigger_type == "absence" and trigger.target_user:
            for user_id, rel in bot_state.relationships.items():
                name = rel.get('display_name', '')
                if name == trigger.target_user:
                    rel['last_proactive_checkin'] = now
                    break

        self._last_trigger_type = trigger.trigger_type
        bot_state.save()

        # Update diversity log
        try:
            history = self._load_diversity_log()
            entry = {
                "timestamp": now,
                "source": trigger.source_category or trigger.trigger_type,
                "summary": message if message else "",
            }
            # Track specific content ID for dedup (e.g. ingestion filename)
            if trigger.content_id:
                entry["content_id"] = trigger.content_id
            history.append(entry)
            self._save_diversity_log(history)
        except Exception as e:
            log_debug(f"Diversity log update failed (non-fatal): {e}")

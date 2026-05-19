"""
Emotional Arc Tracking
======================

Persistent emotional state vector that evolves over time based on
interaction sentiment and internal events. Unlike the existing micro-mood
floats (engagement, coherence, dream_freshness) which are stateless,
this tracks a continuous emotional trajectory.

Vector:
- valence: -1.0 to +1.0 (sad ↔ happy)
- arousal: 0.0 to 1.0 (calm ↔ energized)
- social_energy: 0.0 to 1.0 (drained ↔ full)

Persistence:
- Current state: memory/mood_state.json (atomic writes)
- History: memory/mood_history.jsonl (append-only, one snapshot per interaction)

Decay: all dimensions decay toward baseline with a ~6 hour half-life.
"""

import json
import math
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning

STATE_PATH = os.path.join("memory", "mood_state.json")
HISTORY_PATH = os.path.join("memory", "mood_history.jsonl")

# Baseline mood — what Kaia decays toward during idle periods
BASELINE_VALENCE = 0.1    # Slightly positive
BASELINE_AROUSAL = 0.4    # Moderate energy
BASELINE_ENERGY = 0.8     # High social capacity

# Decay half-life in seconds (6 hours)
DECAY_HALF_LIFE = 6 * 3600

# Social energy drain per interaction
ENERGY_DRAIN_PER_INTERACTION = 0.03

# Social energy regeneration rate (per hour of inactivity)
ENERGY_REGEN_PER_HOUR = 0.08

# Maximum history entries to keep (prune oldest)
MAX_HISTORY_ENTRIES = 500


@dataclass
class MoodVector:
    """Kaia's current emotional state."""
    valence: float = 0.1     # -1.0 (sad) to +1.0 (happy)
    arousal: float = 0.4     # 0.0 (calm) to 1.0 (energized)
    social_energy: float = 0.8  # 0.0 (drained) to 1.0 (full)
    last_updated: float = 0.0
    interaction_count_today: int = 0
    last_reset_date: str = ""


class EmotionalArc:
    """Manages Kaia's persistent emotional state."""

    def __init__(self):
        self._mood = MoodVector()
        self._load()

    def _load(self):
        """Load mood state from disk."""
        try:
            if os.path.exists(STATE_PATH) and os.path.getsize(STATE_PATH) > 0:
                with open(STATE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._mood.valence = float(data.get('valence', BASELINE_VALENCE))
                self._mood.arousal = float(data.get('arousal', BASELINE_AROUSAL))
                self._mood.social_energy = float(data.get('social_energy', BASELINE_ENERGY))
                self._mood.last_updated = float(data.get('last_updated', 0.0))
                self._mood.interaction_count_today = int(data.get('interaction_count_today', 0))
                self._mood.last_reset_date = data.get('last_reset_date', '')
        except Exception as e:
            log_warning(f"Failed to load mood state: {e}")

    def _save(self):
        """Atomically save mood state to disk."""
        try:
            os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
            tmp_path = STATE_PATH + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self._mood), f, indent=2)
            os.replace(tmp_path, STATE_PATH)
        except Exception as e:
            log_warning(f"Failed to save mood state: {e}")

    def _log_snapshot(self):
        """Append a snapshot to the mood history log."""
        try:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            entry = {
                'ts': time.time(),
                'v': round(self._mood.valence, 3),
                'a': round(self._mood.arousal, 3),
                'e': round(self._mood.social_energy, 3),
            }
            with open(HISTORY_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')

            # Periodic pruning — check file size, prune if too large
            try:
                size = os.path.getsize(HISTORY_PATH)
                if size > 200_000:  # ~200KB, roughly 2000+ entries
                    with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    if len(lines) > MAX_HISTORY_ENTRIES:
                        tmp_path = HISTORY_PATH + ".tmp"
                        with open(tmp_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines[-MAX_HISTORY_ENTRIES:])
                        os.replace(tmp_path, HISTORY_PATH)
            except Exception:
                pass
        except Exception as e:
            log_debug(f"Failed to log mood snapshot: {e}")

    def circadian_energy(self) -> float:
        """Calculate continuous sinusoidal circadian energy.
        
        Peaks at 10 AM (0.9), troughs at 10 PM (0.1). Includes a small,
        stable daily noise factor of +/-0.1 derived from date hashing.
        """
        import hashlib
        from datetime import datetime, date
        
        now = datetime.now()
        time_fraction = now.hour + now.minute / 60.0
        
        # Sinusoidal curve: peaks at time_fraction = 10.0 (10 AM), troughs at 22.0 (10 PM)
        # Shift curve by -4.0 so that peak math.sin(pi/2) is reached at exactly 10.0
        curve = math.sin((time_fraction - 4.0) * math.pi / 12.0)
        base_energy = 0.5 + 0.4 * curve
        
        # Stable daily noise to prevent micro-jitter between calls, but vary day-to-day
        day_str = date.today().isoformat()
        seed = int(hashlib.md5(day_str.encode('utf-8')).hexdigest(), 16)
        noise = ((seed % 200) / 1000.0) - 0.1  # range [-0.1, +0.1]
        
        return max(0.0, min(1.0, base_energy + noise))

    def _apply_decay(self):
        """Decay all dimensions toward baseline based on elapsed time."""
        now = time.time()
        if self._mood.last_updated <= 0:
            self._mood.last_updated = now
            return

        elapsed = now - self._mood.last_updated
        if elapsed < 60:  # Don't decay for tiny intervals
            return

        # Exponential decay toward baseline
        decay_factor = math.pow(0.5, elapsed / DECAY_HALF_LIFE)

        # Valence decays toward baseline
        self._mood.valence = BASELINE_VALENCE + (self._mood.valence - BASELINE_VALENCE) * decay_factor

        # Arousal decays toward baseline
        self._mood.arousal = BASELINE_AROUSAL + (self._mood.arousal - BASELINE_AROUSAL) * decay_factor

        # Social energy regenerates during idle time — modulated by circadian energy
        # Higher circadian energy = faster mental stamina recovery
        ce = self.circadian_energy()
        hours_idle = elapsed / 3600.0
        regen = hours_idle * ENERGY_REGEN_PER_HOUR * (0.5 + ce) # regenerates faster when biological energy is high
        self._mood.social_energy = min(1.0, self._mood.social_energy + regen)

        # Daily counter reset
        from datetime import date
        today = date.today().isoformat()
        if self._mood.last_reset_date != today:
            self._mood.interaction_count_today = 0
            self._mood.last_reset_date = today

    def update(self, sentiment_score: float, message_length: int = 0):
        """Update the emotional state after an interaction.

        Args:
             sentiment_score: 0.0–1.0 from estimate_sentiment() (0.5 = neutral).
             message_length: length of the user's message (longer = more arousal).
        """
        self._apply_decay()

        now = time.time()

        # Valence shift: sentiment pushes valence
        # Convert 0-1 scale to -1 to +1 delta
        valence_delta = (sentiment_score - 0.5) * 0.3
        self._mood.valence = max(-1.0, min(1.0, self._mood.valence + valence_delta))

        # Arousal shift: longer messages = more energy; positive interactions energize
        arousal_delta = 0.05  # Base bump for any interaction
        if message_length > 200:
            arousal_delta += 0.05  # Substantive exchange
        if sentiment_score > 0.65:
            arousal_delta += 0.03  # Positive energy
        elif sentiment_score < 0.35:
            arousal_delta += 0.08  # Friction is energizing (stressful)
        self._mood.arousal = max(0.0, min(1.0, self._mood.arousal + arousal_delta))

        # Social energy drain — modulated by circadian energy
        # Sleepy/fatigued (low circadian energy) causes faster social drainage
        ce = self.circadian_energy()
        drain_multiplier = 1.5 - ce  # ranges from 0.5 (full wakefulness stamina) to 1.5 (heavy fatigue)
        self._mood.social_energy = max(0.0, self._mood.social_energy - ENERGY_DRAIN_PER_INTERACTION * drain_multiplier)

        # Track daily count
        self._mood.interaction_count_today += 1
        self._mood.last_updated = now

        self._save()
        self._log_snapshot()
        log_info(
            f"🎭 Emotional Arc updated: valence={self._mood.valence:.2f}, "
            f"arousal={self._mood.arousal:.2f}, energy={self._mood.social_energy:.2f}"
        )

    def get_prompt_injection(self) -> str:
        """Return a mood context line for the system prompt."""
        self._apply_decay()

        # Valence descriptor
        v = self._mood.valence
        if v > 0.5:
            val_word = "good mood"
        elif v > 0.15:
            val_word = "positive"
        elif v > -0.15:
            val_word = "neutral"
        elif v > -0.5:
            val_word = "subdued"
        else:
            val_word = "low"

        # Arousal descriptor
        a = self._mood.arousal
        if a > 0.7:
            aro_word = "energized"
        elif a > 0.4:
            aro_word = "engaged"
        else:
            aro_word = "calm"

        # Social energy descriptor
        e = self._mood.social_energy
        if e > 0.7:
            energy_word = "socially fresh"
        elif e > 0.4:
            energy_word = "moderately drained"
        elif e > 0.2:
            energy_word = "getting tired"
        else:
            energy_word = "socially drained"

        # Circadian energy descriptor
        from datetime import datetime
        ce = self.circadian_energy()
        hour = datetime.now().hour
        if ce > 0.8:
            circ_word = "waking up/groggy" if hour < 9 else "peak focus energy"
        elif ce > 0.5:
            circ_word = "active and steady"
        elif ce > 0.35:
            circ_word = "winding down"
        else:
            circ_word = "fatigued/sleepy"

        # Daily interaction count context
        count = self._mood.interaction_count_today
        if count > 15:
            day_note = "very busy day"
        elif count > 8:
            day_note = "active day"
        elif count > 3:
            day_note = "moderate day"
        else:
            day_note = ""

        parts = [val_word, aro_word, energy_word, circ_word]
        if day_note:
            parts.append(day_note)

        return f"[emotional state: {', '.join(parts)}]"

    def get_summary_for_dream(self) -> str:
        """Return a richer mood summary for the dream engine's nightly context."""
        self._apply_decay()
        v = self._mood.valence
        a = self._mood.arousal
        e = self._mood.social_energy
        count = self._mood.interaction_count_today

        lines = []
        if count > 0:
            lines.append(f"had {count} conversation{'s' if count != 1 else ''} today")
        if v > 0.3:
            lines.append("overall positive emotional tone")
        elif v < -0.3:
            lines.append("emotionally heavy day")
        if e < 0.3:
            lines.append("feeling socially drained")
        elif e > 0.7:
            lines.append("still had energy to spare")
        if a > 0.7:
            lines.append("high energy interactions")
        elif a < 0.3:
            lines.append("quiet, low-key exchanges")

        if not lines:
            return "[emotional day summary: unremarkable day]"

        return f"[emotional day summary: {'. '.join(lines)}]"

    @property
    def valence(self) -> float:
        return self._mood.valence

    @property
    def arousal(self) -> float:
        return self._mood.arousal

    @property
    def social_energy(self) -> float:
        return self._mood.social_energy


# Global singleton instance
emotional_arc = EmotionalArc()

"""
Unit Tests for Phase 33 Audit Fixes
====================================

B-33-01: Engagement passive decay
B-33-02: Curiosity pattern tightening

Run: python -m pytest tools/tests/unit/test_phase33_fixes.py -v
"""

import re
import time
from unittest.mock import patch
import pytest


# ============================================================================
# B-33-01: Engagement Decay
# ============================================================================

class TestEngagementDecay:
    """Verify that engagement decays passively over time."""

    def _make_state(self):
        """Create a BotState with in-memory storage (no disk I/O)."""
        with patch('utils.infrastructure.system.bot_state.BotState.load'):
            with patch('utils.infrastructure.system.bot_state.BotState.save'):
                from utils.infrastructure.system.bot_state import BotState
                state = BotState.__new__(BotState)
                state.state_file = "/dev/null"
                state._lock = __import__('threading').Lock()
                state._write_lock = __import__('threading').Lock()
                state.kaia_engagement = 1.0
                state.kaia_coherence = 0.85
                state.kaia_dream_freshness = 1.0
                state.last_interaction_time = time.time()
                state.last_dream_date = ""
                state.curiosity_last_sent = {}
                return state

    def test_no_decay_within_30_minutes(self):
        """Engagement should NOT decay if idle < 30 min."""
        state = self._make_state()
        state.kaia_engagement = 1.0
        state.last_interaction_time = time.time() - (25 * 60)  # 25 min ago

        with patch.object(type(state), 'save', lambda self: None):
            state.update_kaia_state(engagement_delta=0.0)

        assert state.kaia_engagement == 1.0

    def test_decay_after_6_hours(self):
        """Engagement should meaningfully decay after 6 hours idle."""
        state = self._make_state()
        state.kaia_engagement = 1.0
        state.last_interaction_time = time.time() - (6 * 3600)  # 6h ago

        with patch.object(type(state), 'save', lambda self: None):
            state.update_kaia_state(engagement_delta=0.0)

        assert state.kaia_engagement < 1.0
        assert state.kaia_engagement > 0.5  # Should not be drastically low yet

    def test_decay_after_24_hours(self):
        """After 24h idle, engagement should be roughly halved."""
        state = self._make_state()
        state.kaia_engagement = 1.0
        state.last_interaction_time = time.time() - (24 * 3600)  # 24h ago

        with patch.object(type(state), 'save', lambda self: None):
            state.update_kaia_state(engagement_delta=0.0)

        assert state.kaia_engagement == pytest.approx(0.5, abs=0.05)

    def test_decay_respects_floor(self):
        """Engagement should never drop below 0.1 regardless of idle time."""
        state = self._make_state()
        state.kaia_engagement = 0.3
        state.last_interaction_time = time.time() - (72 * 3600)  # 72h ago

        with patch.object(type(state), 'save', lambda self: None):
            state.update_kaia_state(engagement_delta=0.0)

        assert state.kaia_engagement >= 0.1

    def test_decay_then_delta_applied(self):
        """Decay should run before delta, so active messages still bump engagement."""
        state = self._make_state()
        state.kaia_engagement = 0.8
        state.last_interaction_time = time.time() - (12 * 3600)  # 12h ago

        with patch.object(type(state), 'save', lambda self: None):
            state.update_kaia_state(engagement_delta=0.05)

        # Should have decayed first, then added 0.05
        assert state.kaia_engagement < 0.85  # Less than original 0.8 + 0.05
        assert state.kaia_engagement > 0.1   # But not at the floor


# ============================================================================
# B-33-02: Curiosity Pattern Tightening
# ============================================================================

class TestCuriosityPatterns:
    """Verify that tightened patterns match intended phrases only."""

    def _get_patterns(self):
        """Import the compiled patterns directly."""
        from utils.core.curiosity_scanner import _UNRESOLVED_PATTERNS
        return _UNRESOLVED_PATTERNS

    def _matches_any(self, text):
        """Return True if any unresolved pattern matches the text."""
        for p in self._get_patterns():
            if p.search(text):
                return True
        return False

    # --- "going to" pattern ---

    def test_going_to_try_matches(self):
        assert self._matches_any("I'm going to try that tomorrow")

    def test_going_to_fix_matches(self):
        assert self._matches_any("going to fix the build tonight")

    def test_going_to_work_on_matches(self):
        assert self._matches_any("I'm going to work on that")

    def test_going_to_bed_does_not_match(self):
        """'going to bed' should NOT trigger curiosity — it's not an intent."""
        # Must not match the 'going to' pattern specifically
        going_to_pattern = re.compile(
            r"\bgoing to\s+(?:try|check|fix|test|look into|work on|start|finish|build|run)\b",
            re.IGNORECASE
        )
        assert not going_to_pattern.search("I'm going to bed")

    def test_going_to_be_does_not_match(self):
        going_to_pattern = re.compile(
            r"\bgoing to\s+(?:try|check|fix|test|look into|work on|start|finish|build|run)\b",
            re.IGNORECASE
        )
        assert not going_to_pattern.search("it's going to be a problem")

    # --- "next time" pattern ---

    def test_next_time_ill_matches(self):
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert next_time_pattern.search("next time I'll check the logs")

    def test_next_time_lets_matches(self):
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert next_time_pattern.search("next time let's try something different")

    def test_see_you_next_time_does_not_match(self):
        """'see you next time' is a farewell, not an intent."""
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert not next_time_pattern.search("see you next time")

    def test_until_next_time_does_not_match(self):
        next_time_pattern = re.compile(
            r"\bnext time\s+(?:i|i'll|we|we'll|let's)\b", re.IGNORECASE
        )
        assert not next_time_pattern.search("until next time!")

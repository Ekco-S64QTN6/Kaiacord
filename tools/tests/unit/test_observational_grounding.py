"""
Tests for observational query grounding enforcement.

Ensures that Kaia's response pipeline detects queries about user
interactions/observations and injects grounding enforcement when
RAG returns no supporting data — preventing fabrication.
"""
import re
import sys
import os

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from utils.core.message_processor import _is_observational_query


# ── _is_observational_query detection ──────────────────────────────────


class TestObservationalQueryDetection:
    """Verify that _is_observational_query correctly identifies queries
    about user chat activity vs. normal conversation."""

    POSITIVE_CASES = [
        "What have you observed in chat today?",
        "what have users been talking about?",
        "has anyone been chatting lately?",
        "who has been talking today?",
        "any interesting conversations today?",
        "what have you noticed about users in the channel?",
        "what are people saying about the update?",
        "tell me about chat activity today",
        "what have you seen in chat recently?",
        "what were users asking about?",
        "Kaia what have you observed in chat with other users today in regards to their knowledge of systems?",
        "what have people been discussing lately?",
        "who has been active in chat?",
        "what do users know about systems?",
    ]

    NEGATIVE_CASES = [
        "how are you?",
        "what's the weather like?",
        "tell me about Python decorators",
        "what is a traceroute?",
        "hey kaia",
        "who is Mark?",
        "what's new in the news?",
        "status",
        "can you help me debug this error?",
        "what do you think about the new voice interface?",
        "explain packet loss",
        "what are your thoughts on linux?",
    ]

    def test_positive_cases(self):
        for query in self.POSITIVE_CASES:
            assert _is_observational_query(query), f"Should detect as observational: '{query}'"

    def test_negative_cases(self):
        for query in self.NEGATIVE_CASES:
            assert not _is_observational_query(query), f"Should NOT detect as observational: '{query}'"


# ── EmergencyContaminationFilter patterns ──────────────────────────────


class TestContaminationFilterObservational:
    """Verify that fabricated user-observation prose is caught by the
    EmergencyContaminationFilter."""

    def test_fabricated_single_user(self):
        from utils.core.response_filter import EmergencyContaminationFilter
        text = "there was one user who asked about the server latency"
        assert EmergencyContaminationFilter._compiled_pattern.search(text), \
            "Should catch 'there was one user who asked...'"

    def test_benign_not_caught(self):
        from utils.core.response_filter import EmergencyContaminationFilter
        text = "packet loss usually indicates a routing problem somewhere between you and the server"
        assert not EmergencyContaminationFilter._compiled_pattern.search(text), \
            "Technical explanation should not trigger contamination filter"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

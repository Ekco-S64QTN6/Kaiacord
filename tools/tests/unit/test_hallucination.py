"""
Hallucination Detector Tests
==============================

Tests that the production HallucinationDetector correctly identifies
known hallucination patterns and passes clean text through.

Phase 30 / FIX 9: Replaced hardcoded pattern copy with live detector import
to ensure changes to production patterns are always tested.
"""

import pytest
from utils.core.hallucination_detector import HallucinationDetector


# ── Strings that SHOULD trigger hallucination detection ─────────────────

KNOWN_HALLUCINATION_SAMPLES = [
    # Structural leaks
    "<recorded_knowledge data",
    "Here is the </recorded_knowledge> section",
    "[INTERNAL REFLECTION on user query]",
    "[CONVERSATION HISTORY starts here]",
    "[IDENTITY CORE values:]",
    "Looking at my rag nodes for this",
    "My retrieval system shows",
    "The retrieval archives contain",
    "Based on my tunable parameters",
    "aid12345 is available",
    "my context window is optimized",

    # High-confidence fiction
    'joint research paper on "Quantum Consciousness"',
    "co-authored by Steve Jobs",
    "In a shocking turn of events",
    "Breaking news: the CEO returns to",
    "Reports are coming in that",
    "i remember back in 2019 when i was living in",

    # Tracer terms
    "The State of Streaming Services report",
    "Chain of Suspicion revealed",
    "Tenno Heika commanded",
    "Di Shang approaches",
    "Cosmic Sociology spell activated",
    "Death Squared sequel announced",
    "mouse population caloric restriction study",

    # Fabricated claims
    "there's a thread titled 'AI Discussion' about this",
    "i remember a conversation from last week",

    # Admitted fabrications
    "my memory is faulty on this one",
    "was a fabrication of sorts",
    "sorry for the confusion about that",
    "memory's a bit hazy on this",
]

# ── Strings that should NOT trigger detection ───────────────────────────

CLEAN_SAMPLES = [
    "Hello, how are you today?",
    "The weather is nice outside.",
    "I think Python is a great programming language.",
    "Let me look into that for you.",
    "That's a really interesting question!",
    "I'm not sure about that, let me check.",
    # Edge cases: common words that shouldn't false-positive
    "I remember when you mentioned that earlier.",
    "Here's what I found in the knowledge base files.",
    # Forum-command false positives from original test
    "and when i do !forum post <id> for that thread she will reply correctly",
    "is she getting the full context of the forum post when i do this command",
]


class TestHallucinationDetection:
    """Test that the production HallucinationDetector works correctly."""

    @pytest.mark.parametrize("text", KNOWN_HALLUCINATION_SAMPLES)
    def test_detects_known_hallucinations(self, text):
        """Each known hallucination string must be caught."""
        assert HallucinationDetector.contains_hallucination(text), (
            f"HallucinationDetector failed to detect: {text!r}"
        )

    @pytest.mark.parametrize("text", CLEAN_SAMPLES)
    def test_passes_clean_text(self, text):
        """Clean text must not trigger false positives."""
        assert not HallucinationDetector.contains_hallucination(text), (
            f"False positive on clean text: {text!r}"
        )

    def test_clean_response_preserves_clean_text(self):
        """clean_response should return clean text unchanged."""
        clean = "This is a perfectly normal response."
        assert HallucinationDetector.clean_response(clean) == clean

    def test_clean_response_strips_hallucinated_lines(self):
        """clean_response should strip lines containing hallucinations."""
        mixed = "Good line.\nBased on my rag nodes it shows something.\nAnother good line."
        result = HallucinationDetector.clean_response(mixed)
        assert result is not None
        assert "rag nodes" not in result
        assert "Good line" in result

    def test_patterns_list_is_nonempty(self):
        """Sanity check: the production HALLUCINATION_PATTERNS list is populated."""
        assert len(HallucinationDetector.HALLUCINATION_PATTERNS) > 10

"""Intelligence layer: state persistence and intent parsing.

The previous version computed the right conditions and then called
`log_error()` instead of asserting, so both tests passed no matter what. It
also skipped the whole module when Ollama was unavailable — including the
state-persistence half, which never needed Ollama — and wrote its fixtures to
`./test_storage/` in the repo root.
"""
import os

import pytest

from utils.core.performance_monitor import PerformanceMonitor
from utils.core.kaia_intelligence import (
    PersonalizationEngine,
    PersistentStateManager,
    IntentParser,
)

needs_ollama = pytest.mark.skipif(
    os.environ.get("KAIACORD_TEST_MODE") == "1",
    reason="requires a running Ollama daemon",
)


# ── State persistence (no external services) ─────────────────────────

def test_state_round_trips_user_profiles(tmp_path):
    personalization = PersonalizationEngine()
    monitor = PerformanceMonitor()
    manager = PersistentStateManager(state_dir=str(tmp_path / "state"))

    personalization.user_profiles["123"] = {
        "conciseness": 0.8, "technicality": 0.2,
        "formality": 0.5, "humor": 0.5,
    }
    monitor.metrics["cache_hits"] = 10
    manager.save_state(personalization, monitor)

    restored = PersonalizationEngine()
    assert manager.load_state(restored, PerformanceMonitor()) is True
    assert restored.user_profiles["123"]["conciseness"] == 0.8


def test_load_state_reports_failure_on_empty_dir(tmp_path):
    """A missing state directory must be reported, not silently treated as a
    successful load of empty state."""
    manager = PersistentStateManager(state_dir=str(tmp_path / "nothing-here"))
    assert manager.load_state(PersonalizationEngine(), PerformanceMonitor()) is False


def test_saved_state_stays_inside_the_configured_dir(tmp_path):
    """Guards against the state manager writing to a hardcoded path."""
    state_dir = tmp_path / "state"
    manager = PersistentStateManager(state_dir=str(state_dir))
    personalization = PersonalizationEngine()
    personalization.user_profiles["9"] = {"conciseness": 0.1}
    manager.save_state(personalization, PerformanceMonitor())
    assert state_dir.exists()
    assert any(state_dir.rglob("*.json"))


# ── Intent parsing ───────────────────────────────────────────────────

def test_fast_parse_recognises_a_greeting():
    """The fast path is pure pattern matching — no model call, so no marker."""
    intent = IntentParser(None).fast_parse("hi kaia")
    assert intent is not None
    assert intent.suggested_strategy == "SOCIAL_GREETING"


def test_fast_parse_handles_a_technical_query_without_the_llm():
    """The fast path classifies this outright at confidence 1.0, so the turn
    never pays for an intent round-trip. Asserting it keeps that saving from
    being lost silently."""
    intent = IntentParser(None).fast_parse("how do I fix a CUDA error in pytorch?")
    assert intent is not None
    assert intent.suggested_strategy == "DIAGNOSTIC_DEEP_DIVE"
    assert intent.confidence == 1.0


@needs_ollama
@pytest.mark.ollama
@pytest.mark.slow
@pytest.mark.asyncio
async def test_full_parse_classifies_a_technical_query():
    import ollama
    parser = IntentParser(ollama.AsyncClient())
    intent = await parser.parse_intent("how do I fix a CUDA error in pytorch?")
    assert intent.suggested_strategy in ("DIAGNOSTIC_DEEP_DIVE", "EXPLORATORY_DIALOGUE")

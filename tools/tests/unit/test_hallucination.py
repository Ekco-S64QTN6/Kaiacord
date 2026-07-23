from utils.core.hallucination_detector import HallucinationDetector

def test_clean_patterns():
    """Verify patterns that should NOT be flagged as hallucinations."""
    safe_phrases = [
        "your context window seems small",
        "fragments of the current context window",
        "checking the retrieval logs",
    ]
    for phrase in safe_phrases:
        assert not HallucinationDetector.contains_hallucination(phrase), \
            f"False positive: '{phrase}' should not be flagged"

def test_hallucination_patterns():
    """Verify patterns that SHOULD be flagged by HallucinationDetector."""
    bad_phrases = [
        "my context window is optimized for your query",
        "the rag nodes suggest you should",
    ]
    for phrase in bad_phrases:
        assert HallucinationDetector.contains_hallucination(phrase), \
            f"False negative: '{phrase}' should be flagged"

def test_contamination_patterns():
    """Verify patterns that SHOULD be flagged by EmergencyContaminationFilter."""
    from utils.core.response_filter import EmergencyContaminationFilter
    bad_phrases = [
        "joint research paper on Quantum Consciousness",
        "co-authored by Steve Jobs",
    ]
    for phrase in bad_phrases:
        assert EmergencyContaminationFilter._compiled_pattern.search(phrase), \
            f"False negative: '{phrase}' should be flagged by EmergencyContaminationFilter"

def test_clean_response_removes_lines():
    response = "This is fine.\nmy context window is optimized.\nThis is also fine."
    cleaned = HallucinationDetector.clean_response(response)
    assert cleaned == "This is fine.\nThis is also fine."

def test_clean_response_returns_none_when_all_contaminated():
    response = "my context window is optimized.\nthe rag nodes suggest this."
    result = HallucinationDetector.clean_response(response)
    assert result is None

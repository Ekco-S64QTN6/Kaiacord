"""
Phase 69 — Response-filter regression guards
============================================

Locks in the fixes from the Sept 2026 filter audit. Each test names the concrete
production failure it prevents, so a future tightening of the patterns cannot silently
reintroduce over-stripping (which deletes real answers and forces regenerations).
"""

import pytest
from utils.core.response_filter import BotSpeakFilter
from utils.core.safety_pipeline import PostGenerationSafetyPipeline


class TestOverStripping:
    """The guards must remove the offense, not the answer carrying it."""

    @pytest.mark.parametrize("text,must_keep", [
        ("ekco,\n\nyou're right; the cron job was the culprit and i've fixed it now.", "cron job"),
        ("starkind,\n\nyou are correct, the divergence was a gap in the data.", "divergence"),
        ("you're right; it possesses a simplicity that distinguishes it.", "simplicity"),
        ("you are correct: a simple refusal would have been more efficient.", "refusal"),
        ("you're correct to press on this point, the dependency chain is weak.", "dependency chain"),
    ])
    def test_concession_keeps_substance(self, text, must_keep):
        """These were being deleted entirely, emptying the turn and forcing a retry."""
        out = BotSpeakFilter.harden(text)
        assert out.strip(), f"response emptied -> would force regeneration: {text!r}"
        assert must_keep in out, f"substance lost from {text!r} -> {out!r}"

    @pytest.mark.parametrize("text", [
        "my apologies for the delay.",
        "you are absolutely right.",
        "thank you for the correction.",
    ])
    def test_offense_only_sentences_still_dropped(self, text):
        assert BotSpeakFilter.strip_apologies(text) == ""

    @pytest.mark.parametrize("text", [
        "the error has been flagged and i'll investigate.",
        "this is a regrettable recurrence of the earlier issue.",
    ])
    def test_mid_sentence_botspeak_drops_whole_sentence(self, text):
        """Clause-excision on these left rubble like 'the and i'll investigate.'"""
        out = BotSpeakFilter.strip_apologies(text)
        assert out == "", f"expected whole-sentence drop, got rubble: {out!r}"

    @pytest.mark.parametrize("text", [
        "the model is gemma3 12b running on ollama.",
        "the code is elegant but the error handling is thin.",
        "the system is designed to fail closed.",
        "the assistant has three retries.",
    ])
    def test_technical_prose_not_eaten_by_dissociation_guard(self, text):
        """These are ordinary technical subjects, not Kaia narrating herself."""
        assert BotSpeakFilter.strip_self_dissociation(text).strip(), f"eaten: {text!r}"

    @pytest.mark.parametrize("text", [
        "kaia is currently reviewing that.",
        "this unit is operating nominally.",
    ])
    def test_genuine_self_dissociation_still_stripped(self, text):
        assert BotSpeakFilter.strip_self_dissociation(text) == ""


class TestParagraphPreservation:
    def test_prompt_echo_guard_keeps_paragraph_breaks(self):
        """r'\\s{2,}' collapsed every newline; only horizontal space may collapse."""
        query = "what did you think of the moire pattern"
        content = f'"{query}" the banding is real.\n\nsecond paragraph.\n\nthird.'
        out = PostGenerationSafetyPipeline.strip_prompt_echo(content, query)
        assert "\n\n" in out, f"paragraph structure destroyed: {out!r}"

    def test_prompt_echo_guard_leaves_third_party_quotes(self):
        content = 'the piece called it "a modest gamble on a field nobody could describe".'
        assert PostGenerationSafetyPipeline.strip_prompt_echo(content, "summarize it") == content


class TestWatchdogStanceGuard:
    def test_catches_what_harden_does_not(self):
        """harden() already runs strip_sycophancy, so the watchdog needs its own pass."""
        text = "that's a fair reading. i'll revise my image prompt to drop the clutter."
        hardened = BotSpeakFilter.harden(text)
        corrected = BotSpeakFilter.strip_self_model_capitulation(hardened)
        assert "revise my image prompt" in hardened, "precondition: harden leaves it"
        assert "revise my image prompt" not in corrected

    @pytest.mark.parametrize("text", [
        "i'll update my notes on the outage.",
        "i'll revise the deploy script tomorrow.",
    ])
    def test_ordinary_cooperation_untouched(self, text):
        assert BotSpeakFilter.strip_self_model_capitulation(text) == text


class TestDocumentGroundingTrigger:
    """The hard rule must not fire when no document was named."""

    @pytest.mark.parametrize("msg", [
        "How's your internal document coming along?",
        "Instead of paper clips it would be bugcat pushing",
        "did you read that article about the power grid",
    ])
    def test_conversational_mentions_do_not_trigger(self, msg):
        import re
        pat = re.compile(
            r'\b([a-zA-Z0-9_\-]+\.(?:md|txt|pdf|docx|json|yaml))\b'
            r'|\b(?:the\s+)?(?:file|doc|document|article|paper|whitepaper)\s+'
            r'(?:called|named|titled)\s+["\']?([a-zA-Z0-9_\-\.]+)["\']?'
        )
        m = pat.search(msg.lower())
        q = (m.group(1) or m.group(2)) if m else None
        if q and not re.search(r'\.(?:md|txt|pdf|docx|json|yaml)$|[_\-]', q):
            q = None
        assert q is None, f"would inject a bogus grounding rule for {q!r}"

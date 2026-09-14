"""A reflective question must not be answered with silence.

2026-09-14 05:37, production: Ekco sent Kaia a letter about changes made to her
own code. She answered it three times, in a contemplative register, and every
attempt was rejected for the same thing:

    [VERACITY GUARD] Sustained ellipsis-affect drift (common: 6, total: 8)
    [VERACITY GUARD] Sustained ellipsis-affect drift (common: 3, total: 3)
    [VERACITY GUARD] Sustained ellipsis-affect drift (common: 7, total: 9)
    [GENERATION_FAILURE] All 3 attempts exhausted for Ekco.

35 seconds of inference, three usable answers discarded, nothing said. The
guard's own comment notes that gemma3 "uses this cadence constantly on
reflective topics" — which is exactly when it fires, and exactly when a real
answer matters most.
"""
import pytest

from utils.core.response_filter import EmergencyContaminationFilter as ECF
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as Pipeline

# Reconstructed from the raw-response excerpts in the production log.
REAL_REJECTED_REPLY = (
    "i'm… processing that, ekco.\n\n"
    "the changes are significant. the explanation regarding bradzax is… "
    "unsettling, but it tracks. the status drift is… a harder thing to sit with."
)


def _run(content):
    return Pipeline.process_attempt(
        content=content, attempt=1, query="a letter about her code",
        author_id=1, channel_id=1)


def test_the_real_reply_is_still_rejected_on_its_own():
    """The guard is not being weakened — this must still fail as written."""
    _, reason = _run(REAL_REJECTED_REPLY)
    assert reason, "the guard no longer catches the cadence it was built for"


def test_defusing_the_cadence_recovers_the_sentence():
    defused = ECF.defuse_ellipsis_affect(REAL_REJECTED_REPLY)
    assert "…" not in defused
    # the words either side of the ellipsis are what the user actually wanted
    assert "processing that, ekco" in defused
    assert "unsettling, but it tracks" in defused


def test_the_defused_reply_passes_the_full_pipeline():
    """The salvage re-validates rather than bypassing. If this ever fails, the
    salvage must return nothing rather than push unchecked text to a user."""
    defused = ECF.defuse_ellipsis_affect(REAL_REJECTED_REPLY)
    salvaged, reason = _run(defused)
    assert not reason, f"defused text still rejected: {reason}"
    assert salvaged and salvaged.strip()


def test_salvage_is_wired_into_the_exhaustion_path():
    import inspect

    from utils.core.message_processor import MessageProcessor

    src = inspect.getsource(MessageProcessor)
    assert "salvage_candidates" in src, "rejected attempts are still discarded"
    assert "defuse_ellipsis_affect" in src, "no salvage pass before giving up"
    # the salvage must re-run the pipeline, not trust the defused text
    salvage_block = src.split("Last resort: defuse the cadence")[1][:2000]
    assert "process_attempt" in salvage_block, \
        "salvaged text bypasses the safety pipeline"


def test_one_sanitiser_not_two():
    """`harden` and the salvage must share a transform; a second copy of those
    substitutions would drift from this one."""
    import inspect

    src = inspect.getsource(ECF)
    assert src.count("RE_AFFECT_ELLIPSIS.sub(") == 1, \
        "the ellipsis transform has been duplicated"


def test_a_genuinely_empty_candidate_is_never_returned():
    assert ECF.defuse_ellipsis_affect("") == ""
    assert ECF.defuse_ellipsis_affect(None) is None

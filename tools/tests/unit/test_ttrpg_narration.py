"""TTRPG narration: truncation and budget.

Players reported a battle narration ending mid-word:

    "...jimjam fought an iron golem, each blow reverberating against the
     construct's unyielding armor. the defenders of o"

Cause: `num_predict = 300` on a prompt that asks for one beat per defender,
with no check that the model had finished a sentence. Ten narration call sites
across the TTRPG published raw model output; none of them checked.
"""
import pytest

from utils.ttrpg.narration import (
    EMBED_DESCRIPTION_LIMIT,
    finish_cleanly,
    fit_embed_description,
    looks_truncated,
    raid_token_budget,
)

REAL_TRUNCATION = (
    "the horn's blast was swallowed quickly by the roar that followed. "
    "jimjam fought an iron golem, each blow reverberating against the "
    "construct's unyielding armor. the defenders of o"
)


# ── Detection ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,truncated", [
    (REAL_TRUNCATION, True),
    ("it ended cleanly.", False),
    ("did it end cleanly?", False),
    ("it ended cleanly!", False),
    ('she said "it ended."', False),
    ("trailing off…", False),
    ("cut mid-wor", True),
    ("", False),
    ("   ", False),
])
def test_looks_truncated(text, truncated):
    assert looks_truncated(text) is truncated


# ── Repair ───────────────────────────────────────────────────────────

def test_the_reported_narration_is_trimmed_to_a_whole_sentence():
    out = finish_cleanly(REAL_TRUNCATION)
    assert out.endswith("unyielding armor.")
    assert "the defenders of o" not in out
    assert not looks_truncated(out)


def test_clean_text_is_returned_unchanged():
    text = "the palisade held. the moogles were unimpressed."
    assert finish_cleanly(text) == text


def test_a_paragraph_with_no_terminal_punctuation_is_kept_not_gutted():
    """Trimming to a sentence boundary must not cost most of the report."""
    text = "a long stretch of narration carrying real detail but no full stop anywhere in it"
    out = finish_cleanly(text)
    assert len(out) > len(text) * 0.8
    assert out.endswith("…")


def test_a_dangling_partial_word_is_dropped():
    out = finish_cleanly("bahamut descended and the ground buckl")
    assert "buckl" not in out


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_stays_empty(text):
    assert finish_cleanly(text) == ""


def test_finish_cleanly_is_idempotent():
    once = finish_cleanly(REAL_TRUNCATION)
    assert finish_cleanly(once) == once


# ── Embed limit ──────────────────────────────────────────────────────

def test_over_long_narration_is_clamped_below_the_embed_limit():
    """Discord raises on an over-long description rather than truncating, which
    would lose the whole post."""
    long_text = ("the horn sounded again and again. " * 300)
    out = fit_embed_description(long_text)
    assert len(out) <= EMBED_DESCRIPTION_LIMIT - 2


def test_clamping_lands_on_a_sentence_boundary():
    out = fit_embed_description("shinryu descended. " * 400)
    assert not looks_truncated(out)


def test_short_narration_is_untouched_by_clamping():
    text = "adamantoise lumbered forward."
    assert fit_embed_description(text) == text


# ── Budget ───────────────────────────────────────────────────────────

def test_budget_grows_with_the_cast():
    """A fixed 300 tokens covered roughly three fights; the reported raid had
    six defenders."""
    assert raid_token_budget(6) > raid_token_budget(3) > raid_token_budget(1)
    assert raid_token_budget(6) > 300


def test_budget_is_bounded():
    """A large raid must not ask for an unbounded generation."""
    assert raid_token_budget(500) == raid_token_budget(1000)
    assert raid_token_budget(500) <= 900


def test_budget_handles_a_degenerate_cast():
    assert raid_token_budget(0) > 0
    assert raid_token_budget(-5) > 0


def test_six_defender_raid_gets_room_for_the_reported_narration():
    """The published text was ~1,100 characters and still unfinished."""
    budget_chars = raid_token_budget(6) * 4      # ~4 chars per token
    assert budget_chars > 1400

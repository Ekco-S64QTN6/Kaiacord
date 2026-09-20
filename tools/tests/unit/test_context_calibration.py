"""The context clamp, calibrated against what prompts actually cost.

`_clamp_to_context_window` budgeted with a hardcoded words->tokens ratio. The
first version used 2.05 and deleted every history turn on five consecutive
production turns. The replacement, 1.75, was "the observed maximum" over those
same five.

Measured on 2026-09-20 over 30 paired samples — the clamp's own estimate against
the `prompt_eval_count` that followed it — 1.75 still overshot by a median of
2,620 tokens. The clamp fired on 30 of 42 turns and cut history to its floor on
every one. The largest real prompt all day was 15,127 against a 15,360 budget:
not one of them would have overflowed.

Ollama reports the true count on every generation, so the ratio does not have to
be guessed at all.
"""
import pytest

from utils.core.message_processor import MessageProcessor


@pytest.fixture
def mp():
    return MessageProcessor.__new__(MessageProcessor)


# The true ratios behind that day's 30 samples.
REAL_RATIOS = [1.75 / r for r in (
    1.17, 1.17, 1.15, 1.19, 1.23, 1.19, 1.13, 1.14, 1.18, 1.13,
    1.20, 1.25, 1.20, 1.19, 1.25, 1.23, 1.21, 1.23, 1.21, 1.24,
    1.06, 1.22, 1.15, 1.23, 1.23, 1.24, 1.20, 1.18, 1.25, 1.21)]


def _feed(mp, ratios, words=9000):
    for r in ratios:
        mp._last_prompt_words = words
        mp._observe_prompt_tokens(int(words * r))


def test_the_seed_is_used_until_there_is_evidence(mp):
    assert mp._calibrated_tokens_per_word() == mp._SEED_TOKENS_PER_WORD
    _feed(mp, REAL_RATIOS[:3])
    assert mp._calibrated_tokens_per_word() == mp._SEED_TOKENS_PER_WORD, (
        "three samples is not a distribution")


def test_it_converges_between_the_observed_median_and_maximum(mp):
    _feed(mp, REAL_RATIOS)
    cal = mp._calibrated_tokens_per_word()
    assert sorted(REAL_RATIOS)[len(REAL_RATIOS) // 2] < cal < max(REAL_RATIOS) * 1.02, (
        f"{cal} is not a sane bound for ratios spanning "
        f"{min(REAL_RATIOS):.2f}-{max(REAL_RATIOS):.2f}")


def test_the_densest_real_prompt_of_the_day_is_no_longer_clamped(mp):
    """estimate 16087 / real 15127 — the one turn genuinely near the budget.
    It was cut to the history floor anyway."""
    _feed(mp, REAL_RATIOS)
    words = 16087 / 1.75            # what the old constant implied
    assert words * mp._calibrated_tokens_per_word() <= 15360


@pytest.mark.parametrize("old_estimate,real", [
    (15350, 13104), (15892, 12745), (15172, 12741), (15557, 12553),
])
def test_prompts_that_fit_are_no_longer_cut(mp, old_estimate, real):
    _feed(mp, REAL_RATIOS)
    assert (old_estimate / 1.75) * mp._calibrated_tokens_per_word() < 15360


def test_a_genuinely_oversized_prompt_still_clamps(mp):
    """The clamp exists because four production turns broke the response
    reserve and the reply shrank to 21 tokens. It has to still fire."""
    _feed(mp, REAL_RATIOS)
    huge_words = 20000
    assert huge_words * mp._calibrated_tokens_per_word() > 15360


def test_the_ratio_is_bounded_in_both_directions(mp):
    """A pool of freak samples must not move it far. Too high deletes her
    memory on every turn; too low under-budgets the reply."""
    _feed(mp, [4.0] * 30)
    assert mp._calibrated_tokens_per_word() <= mp._MAX_TOKENS_PER_WORD
    mp2 = MessageProcessor.__new__(MessageProcessor)
    _feed(mp2, [0.6] * 30)
    assert mp2._calibrated_tokens_per_word() >= mp2._MIN_TOKENS_PER_WORD


@pytest.mark.parametrize("words,count", [
    (9000, None), (9000, "n/a"), (9000, 0), (9000, -5),
    (10, 20),              # prompt too small to be representative
    (9000, 99_999_999),    # ratio far outside anything real
])
def test_bad_observations_never_enter_the_pool(mp, words, count):
    _feed(mp, REAL_RATIOS)
    before = list(mp._tpw_samples)
    mp._last_prompt_words = words
    mp._observe_prompt_tokens(count)
    assert list(mp._tpw_samples) == before


def test_observing_before_any_clamp_ran_does_not_raise(mp):
    """`_last_prompt_words` is only set inside the clamp; the first generation
    of a process can report a count before that ever happened."""
    mp._observe_prompt_tokens(12000)
    assert mp._calibrated_tokens_per_word() == mp._SEED_TOKENS_PER_WORD

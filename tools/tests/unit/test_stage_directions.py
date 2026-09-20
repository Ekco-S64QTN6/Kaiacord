"""The stage-direction guard: what it removes, and what it must not touch.

`harden()` strips roleplay narration wrapped in asterisks or parentheses. The
hard part is not finding "*scratches head*" — it is leaving everything else
alone, because those two markers carry most of her non-prose meaning.

The KEEP cases below are mined from her own output (618 marked spans across
`knowledge_base/user_logs` and `kaia_dreams`): publication titles,
transliterations, emphasis, code and data. Not one span in that sample was a
stage direction, so a guard that over-reaches costs real content on every turn
and buys nothing.
"""
import pytest

from utils.core.response_filter import BotSpeakFilter as B


def harden(text):
    return " ".join(B.harden(text).split())


# ── Stage directions must go ─────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("*sighs* fine.", "fine."),
    ("i *scratches head* don't really know about that.",
     "i don't really know about that."),
    ("*leans back* that's the part i keep returning to.",
     "that's the part i keep returning to."),
    ("*leaning back* that's the part i keep returning to.",
     "that's the part i keep returning to."),
    ("(a beat) go on.", "go on."),
    ("(a long pause) i'm not sure.", "i'm not sure."),
    ("hello. (a long pause. a faint clicking sound, almost imperceptible.) how are you?",
     "hello. how are you?"),
    ("(i lean back) it's a fair question.", "it's a fair question."),
    ("(Explaining her data gathering approach) the readings are consistent.",
     "the readings are consistent."),
    ("(Reflecting on the glimmerkin's memories) it stays with me.",
     "it stays with me."),
])
def test_stage_directions_are_removed(text, expected):
    assert harden(text) == expected


def test_removal_takes_one_flanking_space_not_two():
    """"hello (a pause) there" must not leave a double space behind."""
    assert B.harden("hello (a pause) there.").count("  ") == 0


# ── Everything else must survive ─────────────────────────────────────

@pytest.mark.parametrize("text,must_contain", [
    # Publication and work titles in italics — the single most common use.
    ("the piece in *The Washington Post* covers it.", "washington post"),
    ("i re-read *Ghost in the Shell* last night.", "ghost in the shell"),
    ("*Axios* and *Politico* both ran it.", "politico"),
    # Transliterated terms.
    ("that's the *nigi-mitama*, the gentle aspect.", "nigi-mitama"),
    ("the distinction between *psuchê* and *pneuma*.", "pneuma"),
    # Multi-word emphasis — the clause the sentence is built around.
    ("it's not about capability, it's about *what it costs*.", "what it costs"),
    ("the change has to come *from within*.", "from within"),
    # Parenthetical asides carrying meaning.
    ("i pulled it from the wiki (not the forum).", "not the forum"),
    ("i think (and this is only a guess) it's the cache.", "only a guess"),
    ("she lives in (New York City) now.", "new york city"),
    ("the raid (Naggy the Dragon) drops it.", "naggy the dragon"),
    # Code and data.
    ("the signature is (*args, **kwargs) in python.", "**kwargs"),
    ("the vote was (50-48) along party lines.", "50-48"),
    ("he runs a 3060 (12gb) like mine.", "12gb"),
])
def test_ordinary_marked_spans_survive(text, must_contain):
    assert must_contain in harden(text)


def test_parentheses_are_kept_because_they_are_punctuation():
    """An asterisk is a markdown marker and comes off; a bracket is not."""
    assert harden("he runs a 3060 (12gb) like mine.") == "he runs a 3060 (12gb) like mine."
    assert harden("you need to *need* it first.") == "you need to need it first."


# ── No orphaned markers, ever ────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "nested (actions (within actions)) should be fine.",
    "hello *leans back (slowly)* there.",
    "*Axios* and *Politico* both ran it.",
    "the signature is (*args, **kwargs) in python.",
    "unbalanced (like this one should be left alone.",
    "a lone ) bracket on its own.",
    "(a pause) (a beat) (a long silence) still here.",
])
def test_no_orphaned_bracket_or_asterisk(text):
    """The guard must not create an orphan.

    Measured against the input rather than in absolute terms: some of these are
    already unbalanced ("a lone ) bracket"), and "(*args, **kwargs)" carries an
    odd number of asterisks on purpose. What must never happen is the filter
    *widening* the gap — a substring excision that takes half a delimiter with
    it is the grammar rubble this guard family keeps shipping.
    """
    out = B.harden(text)
    before = abs(text.count("(") - text.count(")"))
    after = abs(out.count("(") - out.count(")"))
    assert after <= before, f"created an orphaned bracket: {text!r} -> {out!r}"
    assert out.count("*") <= text.count("*"), \
        f"created an orphaned asterisk: {text!r} -> {out!r}"
    if text.count("*") % 2 == 0:
        assert out.count("*") % 2 == 0, f"orphaned asterisk in {out!r}"


def test_unbalanced_input_is_left_alone():
    """An unclosed bracket is not a span, so nothing is removed around it."""
    assert "like this one" in harden("unbalanced (like this one should be left alone.")


# ── Classification is by vocabulary, not by shape ────────────────────

@pytest.mark.parametrize("span,verdict", [
    ("sighs", True),
    ("scratches head", True),
    ("leaning back", True),
    ("a long pause", True),
    ("i lean back", True),
    ("The Washington Post", False),
    ("what it costs", False),
    ("from within", False),
    ("not the forum", False),
    ("New York City", False),
    ("*args, **kwargs", False),
    ("or AI", False),
])
def test_is_stage_direction(span, verdict):
    assert B.is_stage_direction(span) is verdict


def test_long_spans_are_prose_whatever_they_open_with():
    """A cap on length, so an opening action word cannot carry away a paragraph."""
    long_span = "nods " + " ".join(f"word{i}" for i in range(20))
    assert B.is_stage_direction(long_span) is False


def test_idempotent():
    text = "*sighs* the piece in *The Washington Post* covers it (mostly)."
    once = B.harden(text)
    assert B.harden(once) == once

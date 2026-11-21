"""Notes that say nothing, or say it about the wrong thing, stay out of the prompt."""
import time
from pathlib import Path

PROC = Path("utils/core/message_processor.py")


def _state(mood="neutral", energy="moderate", intent="casual_chat"):
    from utils.infrastructure.system import bot_state as bsm
    bs = bsm.BotState.__new__(bsm.BotState)
    bs.user_states = {"1": {"apparent_mood": mood, "energy": energy, "likely_intent": intent,
                            "updated_at": time.time()}}
    return bs


def test_a_reading_of_nothing_is_not_a_read_on_someone():
    assert _state().get_user_state_read("1", "Ekco") == ""


def test_only_what_was_read_is_said():
    assert _state(mood="frustrated").get_user_state_read("1", "Ekco") == "[your read on Ekco: seems frustrated]"
    assert _state(energy="high", intent="asking_questions").get_user_state_read("1", "Ekco") \
        == "[your read on Ekco: energy high, likely asking questions]"


def test_the_identity_stream_is_shown_in_whole_entries():
    from utils.core.message_processor import recent_entries
    stream = ("**2026-11-09**\n" + "i looked at old network diagrams again. " * 30
              + "\n\n---\n**2026-11-10**\ni've been letting some things be.\n\n---\n"
              "**2026-11-11**\ni keep looking for an architecture in everything.")
    shown = recent_entries(stream, 800)
    assert shown.startswith("**2026-11-10**")              # never mid-word, mid-entry
    assert shown.endswith("architecture in everything.")
    assert "2026-11-09" not in shown and len(shown) <= 800


def test_one_long_entry_is_cut_back_to_a_sentence_start():
    from utils.core.message_processor import recent_entries
    shown = recent_entries("**2026-11-11**\n" + "this is one sentence of the entry. " * 60, 300)
    assert len(shown) <= 300 and shown.startswith("this is one sentence")
    assert recent_entries("", 800) == ""


def test_no_injection_gives_length_advice():
    """Length has one owner (turn_shape). The hour said "willing to go longer" at
    night, and a fatigue note said "your responses should be getting shorter" from
    the fifteenth message of a session (41 of 85 replies on 18 Nov)."""
    import inspect
    from utils.core.message_processor import MessageProcessor
    src = inspect.getsource(MessageProcessor._retrieve_and_generate)
    for phrase in ("shorter responses", "responses should be getting shorter", "brief answers",
                   "go longer", "balanced responses", "match their brevity", "fuller responses"):
        assert phrase not in src, phrase


def test_a_recently_read_file_is_mentioned_only_when_the_turn_touches_it():
    src = PROC.read_text(encoding="utf-8")
    block = src[src.index('# 8i. "I\'ve Been Reading" Mentions'):src.index("# 8j. Claim verification")]
    assert "_title_words & set(content_words(ctx.own_words" in block

"""What she did ("[i played records …]") is history, not a line she says next."""
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P

SET = "[i played records in general for 1 minutes — 1 of them, starting with paul van dyk — for an angel (pvd arcade mix); ekco listened.]"
REPLY = ("understood, starkind.\n\nyour assessment is accurate. the prompt sequence was intended as a "
         "self-contained exploration, free from external influence.\n\nthe clarification regarding the "
         "observation is appreciated.\n\n" + SET)


def test_an_event_line_copied_onto_a_reply_is_dropped():
    out = P.strip_event_echo(REPLY)
    assert SET not in out and out.endswith("the clarification regarding the observation is appreciated.")
    assert P.strip_event_echo("i played records last night for an hour, it was fun.") == \
        "i played records last night for an hour, it was fun."            # prose, not the bracketed line
    assert P.strip_event_echo(SET) == SET                                  # never empties a reply


def test_the_prompt_shows_an_event_as_a_note_not_her_turn():
    history = [{"role": "user", "content": "how's it going"},
               {"role": "assistant", "content": SET, "event": True},
               {"role": "assistant", "content": '[i made a piece called "tide"]'},     # an older, unmarked one
               {"role": "user", "content": "nice"},
               {"role": "assistant", "content": REPLY}]
    out = P.events_as_notes(history)
    assert out[1]["role"] == "system" and out[1]["content"].startswith("[earlier in this channel")
    assert out[2]["role"] == "system"
    assert SET not in out[4]["content"] and out[4]["role"] == "assistant"
    assert out[0] == history[0] and out[3] == history[3]


def test_remember_marks_the_line_as_an_event(monkeypatch):
    from collections import deque
    from utils.core import kaia_expression
    from utils.infrastructure.system.bot_state import bot_state
    from utils.core.kaia_desires import desire_engine
    monkeypatch.setattr(bot_state, "channel_memory", {})
    monkeypatch.setattr(desire_engine, "observe_creation", lambda: None)
    kaia_expression.remember("music", SET, channel_id=5)
    turn = list(bot_state.channel_memory[5])[-1]
    assert turn["event"] is True and turn["role"] == "assistant"

"""What she is shown should agree with the persona, which is the root of how
she sounds: a rule the reply filters enforce after the fact is weaker than a
prompt that does not teach the opposite."""
import time
from pathlib import Path
from unittest.mock import MagicMock

PROC = Path("utils/core/message_processor.py")


def _ctx(text="hey"):
    from utils.core.message_context import MessageContext
    author = MagicMock()
    author.display_name = author.name = "Ekco"
    author.id = 177011971818782721
    msg = MagicMock()
    msg.platform, msg.author, msg.content, msg.attachments = "discord", author, text, []
    msg.channel.id = 1
    ctx = MessageContext(message=msg, sanitized_content=text, is_social=False, is_mention=True,
                         is_dm=False, start_time=0.0)
    ctx.category = "general"
    return ctx


def _system(persona_text, appended, text="hey"):
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config
    p = MessageProcessor.__new__(MessageProcessor)
    p.config = config
    ctx = _ctx(text)
    ctx.persona_text = persona_text
    return p._construct_messages(ctx, {"persona": persona_text + appended, "rag": "", "history": []})[0]["content"]


def test_notes_after_the_persona_carry_no_dashes_and_the_persona_is_untouched():
    """From 3 Nov the em dash, which the persona forbids, was in 45-64% of her
    replies; the prompt she was shown was full of them."""
    persona = "# persona\nthe haze is about past chats — never facts.\n"
    out = _system(persona, "\n\n[time: evening — relaxed.]\n\n[how you see ekco: steady – kind.]")
    assert out.startswith(persona)                       # still the prefix the warm-up cached
    assert "—" not in out[len(persona):]
    assert "[time: evening, relaxed.]" in out and "steady, kind." in out


def test_a_name_on_its_own_is_not_answered_with_a_probing_question():
    """Persona: "Don't respond to casual greetings with probing questions … just say hi back."""
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config
    p = MessageProcessor.__new__(MessageProcessor)
    p.config = config
    user_turn = p._construct_messages(_ctx("kaia"), {"persona": "P", "rag": "", "history": []})[-1]["content"]
    assert "say hi back" in user_turn.lower() and "ask what's up" not in user_turn.lower()


def test_her_history_is_shown_without_dashes():
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    hist = [{"role": "user", "content": "starkind: a—b"},
            {"role": "assistant", "content": "the same illusions—regardless of how much data."}]
    shown = P.detemplate_history(hist)
    assert shown[1]["content"] == "the same illusions, regardless of how much data."
    assert shown[0]["content"] == hist[0]["content"]       # what a person typed is theirs
    assert P.undash("1990–1995 was a long stretch") == "1990–1995 was a long stretch"


def test_the_identity_stream_comes_after_the_persona():
    """Prepended, it moved the prompt's first tokens with every dream, so the
    persona the warm-up caches never matched the start of a real prompt."""
    src = PROC.read_text(encoding="utf-8")
    block = src[src.index("identity_stream = self._identity_cache.get"):]
    block = block[:block.index("log_debug(f\"Identity stream injected")]
    assert block.index("{ctx.system_prompt}") < block.index("RECENT PERSPECTIVE SHIFTS")


def test_the_dossier_does_not_call_a_repair_message_s_words_topics(monkeypatch):
    """"recent topics: begin, meant, sorry" came from the words of "i meant pry
    not pray sorry", stored on a repair event to recognise a repeat."""
    from utils.infrastructure.system import bot_state as bsm
    from utils.core import relationship_manager, memory_anchors
    bs = bsm.BotState.__new__(bsm.BotState)
    bs._dossier_primed_users = {}
    bs.relationships = {"1": {"last_seen": time.time() - 3 * 3600, "interaction_count": 600,
                              "first_seen": time.time() - 9e6, "topic_counts": {}}}
    ev = MagicMock(timestamp=time.time(), topics=["begin", "meant", "sorry"])
    monkeypatch.setattr(relationship_manager, "load_events", lambda uid: [ev])
    monkeypatch.setattr(memory_anchors, "_load_anchors", lambda: [])
    out = bs.get_user_dossier("1", "starkind")
    assert "begin" not in out and "recent topics" not in out
    assert "interests: varied" not in bs.get_relationship_summary("1", "starkind")

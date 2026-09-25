"""Code she writes reaches Discord as code."""
from utils.core import code_blocks
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P

CODE = "```python\ndef f(x):\n    if x:\n        return 1\n    return 0\n```"


def test_code_survives_the_pipeline_byte_for_byte():
    reply = f"The loop never exits because the counter never moves.\n\n{CODE}\n\nThat should do it."
    out, reason = P.process_attempt(content=reply, attempt=1, query="why does my loop hang")
    assert reason is None and CODE in out
    assert out.startswith("the loop never exits")          # prose still filtered


def test_a_reply_that_is_only_code_is_kept():
    out, reason = P.process_attempt(content=CODE, attempt=1, query="write me a function")
    assert reason is None and out == CODE


def test_a_fence_around_prose_is_still_removed():
    out, _ = P.process_attempt(content="```\nhonestly the book is better than the film.\n```",
                               attempt=1, query="book or film?")
    assert "```" not in out and "book is better" in out


def test_prose_is_not_mistaken_for_code():
    assert not code_blocks.looks_like_code("for the record, if you want my take, it's fine.\nno rush.")
    assert code_blocks.looks_like_code("$ sudo pacman -Syu\n$ reboot")


def test_a_block_whose_placeholder_was_dropped_is_appended():
    text, blocks = code_blocks.stash(f"intro.\n\n{CODE}")
    assert code_blocks.restore("intro.", blocks).endswith(CODE)


def test_the_safety_pipeline_is_given_the_speakers_words():
    """The echo guards compare her reply with the user's message; given the
    enriched message they deleted her quotes from a linked article."""
    from pathlib import Path
    src = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    assert "query=getattr(ctx, 'sanitized_content'" not in src
    assert "strip_echoed_query(\n            ctx.response_text, ctx.own_words)" in src

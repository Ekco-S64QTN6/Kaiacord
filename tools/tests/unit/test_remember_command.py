"""'kaia remember' stores what the user typed, never the enrichment around it."""
import asyncio
from types import SimpleNamespace

from utils.commands.memory_handler import handle_memory_command


class _Chan:
    def __init__(self):
        self.sent = []

    async def send(self, embed=None, **_):
        self.sent.append(embed)


def _run(content):
    stored = []

    async def run_rag(fn, uid, name, text):
        stored.append(text)
        return True

    msg = SimpleNamespace(channel=_Chan(), author=SimpleNamespace(id=1, display_name="Ekco"))
    handled = asyncio.run(handle_memory_command(msg, content, run_rag, SimpleNamespace(add_memory=None)))
    return handled, stored


def test_a_linked_page_is_not_stored_as_the_memory():
    handled, stored = _run("kaia remember this: the pond freezes in december\n\n"
                           "[LINKED_WEB_CONTENT]\nforty lines of somebody's article")
    assert handled and stored == ["the pond freezes in december"]


def test_a_when_in_the_quoted_post_does_not_block_it():
    handled, stored = _run("[REPLYING_TO]\nLune: remember when we raided?\n\n"
                           "[USER_MESSAGE]\nkaia remember that my cat is lucky")
    assert handled and stored == ["my cat is lucky"]


def test_a_question_is_still_not_a_memory():
    assert _run("kaia remember when we met?") == (False, [])

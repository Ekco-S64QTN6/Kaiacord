"""Every `!` command and alias, typed by an ordinary member and by the owner,
with no argument and with a wrong one, either answers or refuses. None may
raise into the dispatcher's "failed. check the logs", stay silent, or send
something Discord would reject.

This is the acceptance matrix for the Discord boundary that can be run without
Discord: the real registry, the real dispatcher and the real handlers, with a
stand-in message, no voice channel, no network and no model. The game's
subcommands have the same check in `ttrpg/test_every_command_answers.py`.
"""
import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from utils.commands import registry
from utils.infrastructure.system.yaml_config import config

OWNER_ID, MEMBER_ID = 111, 700000009
INVOCATIONS = sorted(word for cmd in registry.COMMANDS for word in cmd.invocations)
#: (label, text after the command word)
ARGUMENTS = (("bare", ""), ("wrong", " zzqx-not-a-thing"), ("hostile", " ../../etc/passwd @everyone"),
             ("long", " " + "word " * 780))          # 3,900 characters: a full Discord message


class _Channel:
    id = 4242
    name = "kaia-opolis"
    guild = None

    def __init__(self, out):
        self.out = out

    async def send(self, *a, **k):
        self.out.append((a, k))
        m = MagicMock()
        m.edit, m.delete, m.add_reaction = AsyncMock(), AsyncMock(), AsyncMock()
        return m

    def typing(self):
        class _T:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
        return _T()

    async def history(self, **_k):
        return
        yield                                     # an empty channel

    def permissions_for(self, _who):
        return discord.Permissions.all()


def _message(content, owner, out):
    msg = MagicMock()
    msg.content = content
    msg.author.id = OWNER_ID if owner else MEMBER_ID
    msg.author.name = "architect" if owner else "tester"
    msg.author.display_name = "Architect" if owner else "Tester"
    msg.author.bot = False
    msg.author.voice = None                       # in no voice channel
    msg.channel = _Channel(out)
    msg.guild.voice_client = None
    msg.mentions, msg.attachments, msg.embeds, msg.stickers, msg.reference = [], [], [], [], None

    async def reply(*a, **k):
        out.append((a, k))
        return MagicMock(edit=AsyncMock(), delete=AsyncMock())
    msg.reply = reply

    async def react(*a, **k):
        out.append((("reaction",), {}))
    msg.add_reaction = react
    return msg


def _context(owner):
    ctx = MagicMock()
    ctx.config.is_owner = MagicMock(return_value=owner)

    async def _no_model(*a, **k):
        raise ConnectionError("no model in this test")
    ctx.ollama_client.chat = _no_model
    ctx.ollama_client.generate = _no_model
    ctx.rag = None
    # What a booted bot holds as numbers, and no chat pipeline behind it.
    ctx.message_processor = None
    ctx.bot_state.kaia_coherence = 0.85
    ctx.bot_state.last_manual_quip_time = 0.0
    ctx.bot_state.save = MagicMock()
    return ctx


def _run(content, owner):
    out = []
    msg = _message(content, owner, out)

    async def respond(channel, text, use_code_block=True, **k):
        out.append(((text,), k))

    async def persona():
        return "persona"

    async def go():
        return await asyncio.wait_for(registry.dispatch_command(_context(owner), msg, persona, respond), 30)
    handled = asyncio.run(go())
    return handled, out


def _embeds(k):
    return [e for e in ([k.get("embed")] + list(k.get("embeds") or [])) if isinstance(e, discord.Embed)]


def _texts(out):
    found = []
    for a, k in out:
        found += [str(x) for x in a if isinstance(x, str)]
        if isinstance(k.get("content"), str):
            found.append(k["content"])
        for e in _embeds(k):
            found += [e.description or "", e.title or ""] + [f"{f.name} {f.value}" for f in e.fields]
    return found


def _limits(out):
    """What Discord would refuse: 2,000 characters of content, a 6,000-character
    embed, 25 fields, 1,024 a field, 25 components in 5 rows."""
    bad = []
    for a, k in out:
        for text in [x for x in a if isinstance(x, str)] + ([k["content"]] if isinstance(k.get("content"), str) else []):
            if len(text) > 2000:
                bad.append(f"content {len(text)} chars")
        for e in _embeds(k):
            if len(e) > 6000 or len(e.fields) > 25 or len(e.description or "") > 4096:
                bad.append(f"embed {len(e)} chars, {len(e.fields)} fields")
            bad += [f"field {f.name!r} {len(f.value)} chars" for f in e.fields if len(f.value) > 1024]
        view = k.get("view")
        if isinstance(view, discord.ui.View) and (len(view.children) > 25 or any((c.row or 0) > 4 for c in view.children)):
            bad.append(f"view with {len(view.children)} components")
    return bad


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """A temporary working directory, the owner known by ID, and no network."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(type(config), "is_owner",
                        lambda self, name="", display=None, uid="": str(uid) == str(OWNER_ID))

    def blocked(*a, **k):
        raise OSError("no network in this test")
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    return tmp_path


@pytest.mark.parametrize("word", INVOCATIONS)
@pytest.mark.parametrize("label,tail", ARGUMENTS, ids=[a[0] for a in ARGUMENTS])
@pytest.mark.parametrize("owner", [False, True], ids=["member", "owner"])
def test_command_answers(offline, word, label, tail, owner):
    cmd = registry.LOOKUP[f"!{word}"]
    handled, out = _run(f"!{word}{tail}", owner)
    assert handled is True
    assert out, f"!{word}{tail} said nothing to {'the owner' if owner else 'a member'}"
    said = " ".join(_texts(out))
    assert "failed. check the logs" not in said.lower(), f"!{word}{tail} raised into the dispatcher"
    assert not _limits(out), _limits(out)
    if cmd.owner_only and not owner:
        assert "restricted" in said.lower(), f"!{word} did not refuse a member: {said[:200]}"
    # Only message content can ping: a mention inside an embed notifies nobody.
    content = " ".join([x for a, k in out for x in a if isinstance(x, str)]
                       + [k["content"] for a, k in out if isinstance(k.get("content"), str)])
    assert "@everyone" not in content, f"!{word} repeated a mass mention"


def test_a_near_miss_is_not_a_command(offline):
    for text in ("!newsletter", "!artist", "!helper", "!rpgx", "! help", "!!help"):
        handled, out = _run(text, False)
        assert handled is False and not out, text

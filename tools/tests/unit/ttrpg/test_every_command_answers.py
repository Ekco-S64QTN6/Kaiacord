"""Every !rpg subcommand, typed, either answers or is an owner-only command.

Four housing commands crashed on every use because the router's send could
not carry an embed, `!rpg shop` crashed for anyone without a character, and
thirty handlers returned nothing at all to a player who had not made one.
The game's state paths are relative to the working directory, so this runs
in a temporary one and never touches memory/ttrpg.
"""
import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Imported here, before the test moves into its temporary directory: the
# config is read relative to the working directory.
import utils.commands.rpg_handler as rh

ROUTER = Path(__file__).resolve().parents[4] / "utils" / "commands" / "rpg_handler.py"
SUBCOMMANDS = sorted(set(re.findall(r'^\s+"([a-z_]+)":', ROUTER.read_text(encoding="utf-8"), re.M)))
OWNER_ONLY = {"bestiary", "xp", "give", "heal", "event"}


class _Channel:
    id = 4242
    name = "general"

    def __init__(self, out):
        self.out = out

    async def send(self, *a, **k):
        self.out.append((a, k))
        m = MagicMock()
        m.edit = AsyncMock()
        return m

    def typing(self):
        class _T:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
        return _T()


def _dispatch(uid, content, out, faults):
    msg = MagicMock()
    msg.content = content
    msg.author.id, msg.author.name, msg.author.display_name = int(uid), "tester", "Tester"
    msg.channel = _Channel(out)
    msg.mentions, msg.attachments = [], []
    ctx = MagicMock()
    ctx.config.is_owner = MagicMock(return_value=False)

    async def _chat(*a, **k):
        return {"message": {"content": "The wind moves."}}
    ctx.ollama_client.chat = _chat

    async def _reply(channel, text, use_code_block=True):
        out.append(((text,), {}))

    real = rh.log_error
    rh.log_error = lambda m, *a, **k: faults.append(m)
    try:
        asyncio.run(asyncio.wait_for(rh.handle_rpg_command(ctx, msg, _reply), 20))
    finally:
        rh.log_error = real


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_a_player_without_a_character_is_always_answered(sandbox):
    silent, faults = [], []
    for sub in SUBCOMMANDS:
        if sub == "new":
            continue
        out = []
        _dispatch("700000001", f"!rpg {sub}", out, faults)
        if not out and sub not in OWNER_ONLY:
            silent.append(sub)
    assert not faults, faults
    assert not silent, f"no reply to: {silent}"


def test_the_housing_commands_can_send_their_embeds(sandbox):
    out, faults = [], []
    _dispatch("700000002", "!rpg new Tess Human Warrior", out, faults)
    for sub in ("home", "farm_view", "water_crops", "treat", "home_training", "shop", "flee"):
        _dispatch("700000002", f"!rpg {sub}", out, faults)
    assert not faults, faults
    assert not (sandbox / "memory").is_symlink()

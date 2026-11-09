"""Every !rpg turn ends on a card with buttons under it (turn_buttons).

A Strange Statue on a hunt sent its card bare: the player had to scroll up to
an older turn's buttons or type `!rpg` again to carry on.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import utils.commands.rpg_handler as rh
from utils.ttrpg import turn_buttons


class _Channel:
    id = 4343
    name = "general"

    def __init__(self):
        self.sent = []          # (kwargs, message)

    async def send(self, *a, **k):
        m = MagicMock()
        m.edit = AsyncMock()
        self.sent.append((k, m))
        return m

    def typing(self):
        class _T:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
        return _T()


def _dispatch(uid, content, channel):
    msg = MagicMock()
    msg.content = content
    msg.author.id, msg.author.name, msg.author.display_name = int(uid), "tester", "Tester"
    msg.channel = channel
    msg.mentions, msg.attachments = [], []
    ctx = MagicMock()
    ctx.config.is_owner = MagicMock(return_value=False)
    ctx.bot.get_channel = MagicMock(return_value=None)

    async def _reply(ch, text, use_code_block=True):
        return await ch.send(content=text)

    asyncio.run(asyncio.wait_for(rh.handle_rpg_command(ctx, msg, _reply), 20))


def _labels(view):
    return [getattr(item, "label", "") for item in view.children]


def _final_view(channel):
    """The view the turn's last card ended with: sent with it, or edited on."""
    kwargs, message = channel.sent[-1]
    if isinstance(kwargs.get("view"), discord.ui.View):
        return kwargs["view"]
    if message.edit.await_args:
        return message.edit.await_args.kwargs.get("view")
    return None


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_a_forest_event_on_a_hunt_leaves_hunt_again_under_its_card(sandbox, monkeypatch):
    from utils.ttrpg import character_manager, encounter_tables, outing

    uid = "700000101"
    ch = _Channel()
    _dispatch(uid, "!rpg new Tess Human Warrior", ch)

    async def _move():
        sheet = await character_manager.load(uid)
        sheet["location"] = "aeridor_ruins"
        await character_manager.save(sheet)
    asyncio.run(_move())

    monkeypatch.setattr(encounter_tables, "roll_for_event", lambda loc: True)
    monkeypatch.setattr(encounter_tables, "random_event", lambda loc: "strange_statue")
    monkeypatch.setattr(outing, "record_event", AsyncMock())

    ch.sent.clear()
    _dispatch(uid, "!rpg hunt", ch)

    titles = [getattr(k.get("embed"), "title", "") for k, _ in ch.sent]
    assert "🗿 Strange Statue" in titles, titles
    view = _final_view(ch)
    assert view is not None, "the event card was left without buttons"
    assert "🗡️ Hunt Again" in _labels(view) and "📊 Status" in _labels(view)


def test_buttons_sent_earlier_in_the_turn_move_down_to_its_last_card():
    async def _turn():
        ch = _Channel()
        view = discord.ui.View()
        async with turn_buttons.turn(MagicMock(), MagicMock(), "1", "u", False):
            tc = turn_buttons.TurnChannel(ch)
            await tc.send(embed=discord.Embed(title="round"), view=view)
            await tc.send(embed=discord.Embed(title="quest complete"))
        first, last = ch.sent[0][1], ch.sent[1][1]
        first.edit.assert_awaited_once_with(view=None)
        last.edit.assert_awaited_once_with(view=view)
    asyncio.run(_turn())


def test_a_turn_ending_with_buttons_or_ephemeral_is_left_alone():
    async def _turn():
        ch = _Channel()
        async with turn_buttons.turn(MagicMock(), MagicMock(), "1", "u", False):
            tc = turn_buttons.TurnChannel(ch)
            await tc.send(embed=discord.Embed(title="card"), view=discord.ui.View())
            await tc.send("not yours", ephemeral=True)
        assert not any(m.edit.await_args for _, m in ch.sent)
    asyncio.run(_turn())


def test_a_player_without_a_character_gets_no_buttons(sandbox):
    ch = _Channel()
    _dispatch("700000102", "!rpg hunt", ch)
    assert ch.sent and _final_view(ch) is None


def test_a_nested_handler_call_is_part_of_the_outer_turn():
    async def _turn():
        ch = _Channel()
        async with turn_buttons.turn(MagicMock(), MagicMock(), "1", "u", False):
            async with turn_buttons.turn(MagicMock(), MagicMock(), "1", "u", False):
                await turn_buttons.TurnChannel(ch).send("inner")
            assert not ch.sent[0][1].edit.await_args      # not finished by the inner scope
    asyncio.run(_turn())

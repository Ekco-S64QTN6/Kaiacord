"""Command routing, help rendering and admin gating.

None of this had any coverage. The dispatcher was a chain of
`content.startswith("!news")` tests, so `!newsletter` reached the news handler
and `!helper` reached help; `!help` was a hand-maintained transcription of the
command list that had already drifted from what the dispatcher accepted; and
`is_owner` matched on Discord *display names*, which a member picks for
themselves.
"""
import inspect

import pytest

from utils.commands import registry
from utils.commands.registry import COMMANDS, LOOKUP, resolve
from utils.infrastructure.system.yaml_config import config


# ── Routing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("!news", "news"),
    ("!news tech", "news"),
    ("!art --seed 3 --palette void", "art"),
    ("!dreams list", "dream"),          # alias
    ("!halloffame", "scores"),          # alias
    ("!HELP", "help"),                  # case-insensitive
    ("  !help  ", "help"),              # surrounding whitespace
])
def test_resolves_command_and_aliases(text, expected):
    cmd = resolve(text)
    assert cmd is not None and cmd.name == expected


@pytest.mark.parametrize("text", [
    "!newsletter",   # would have routed to !news
    "!artist",       # would have routed to !art
    "!explained",    # would have routed to !explain
    "!cached",       # would have routed to !cache
    "!helper",       # would have routed to !help
    "!rpgx",         # would have routed to !rpg
    "!nope",
    "hello there",
    "",
    "!",
])
def test_rejects_near_misses_and_non_commands(text):
    """Matching is on the whole first word, not a prefix."""
    assert resolve(text) is None


def test_every_invocation_is_unique():
    """_build_lookup raises on a duplicate, but assert it stays that way."""
    seen = [w for cmd in COMMANDS for w in cmd.invocations]
    assert len(seen) == len(set(seen))


def test_lookup_covers_every_command():
    assert len(LOOKUP) == sum(len(c.invocations) for c in COMMANDS)


# ── Handler wiring ───────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", COMMANDS, ids=lambda c: c.name)
def test_handler_signature_matches_declared_extras(cmd):
    """The table says which extra argument a handler wants; if that is wrong
    the command raises TypeError the first time anyone runs it."""
    sig = inspect.signature(cmd.handler)
    expected = 2 if cmd.extra is None else 3
    required = sum(
        1 for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )
    assert required <= expected <= len(sig.parameters), (
        f"!{cmd.name} declares extra={cmd.extra} (so {expected} args) but its "
        f"handler signature is {sig}"
    )


@pytest.mark.parametrize("cmd", COMMANDS, ids=lambda c: c.name)
def test_owner_only_flag_matches_the_handler_gate(cmd):
    """!help renders from `owner_only`, so a wrong flag either hides a usable
    command or advertises one that will refuse."""
    # !forum gates most subcommands but lets `!forum link <uid>` through before
    # the check, so the command as a whole is not owner-only.
    if cmd.name == "forum":
        assert cmd.owner_only is False, (
            "!forum must stay discoverable: `!forum link` is a user command"
        )
        return
    try:
        source = inspect.getsource(cmd.handler)
    except OSError:
        pytest.skip("source unavailable")
    # A real gate returns early with a refusal. Wording varies between
    # handlers ("restricted.", "you aren't my architect. restricted."), so
    # match on the word they all share.
    gated = "is_owner" in source and "restricted" in source.lower()
    assert gated == cmd.owner_only, (
        f"!{cmd.name}: table says owner_only={cmd.owner_only}, handler "
        f"{'has' if gated else 'has no'} an owner gate"
    )


# ── Admin authorization ──────────────────────────────────────────────

def test_owner_is_recognised_by_username():
    assert config.is_owner("ekco", "Ekco", "177011971818782721") is True


def test_owner_is_recognised_by_user_id_alone():
    """Guards against a username change locking the operator out."""
    assert config.is_owner("some_new_handle", "whatever", "177011971818782721") is True


def test_display_name_alone_does_not_grant_admin():
    """The escalation this replaced: a member sets their server nickname to the
    owner's name and gains `!reindex --full`, `!enrich`, `!memory`, `!forum`,
    `!snapshot`, `!selfmodel`, `!sysmon` and `!dream generate`."""
    assert config.is_owner("mallory", "Ekco", "999999999999999999") is False


def test_ordinary_user_is_not_an_owner():
    assert config.is_owner("mallory", "mallory", "999999999999999999") is False


def test_trailing_period_usernames_still_match():
    """Discord appends a period to some legacy usernames."""
    assert config.is_owner("ekco.", None, "1") is True


# ── Help rendering ───────────────────────────────────────────────────

def _help(is_owner, content="!help"):
    import asyncio
    from unittest.mock import MagicMock
    from utils.commands.help_handler import handle_help_command

    ctx = MagicMock()
    ctx.config.is_owner.return_value = is_owner
    msg = MagicMock()
    msg.content = content
    msg.author.name = "u"
    msg.author.display_name = "u"
    msg.author.id = 1
    sent = []

    async def send(embed=None, view=None):
        sent.append((embed, view))

    msg.channel.send = send
    asyncio.run(handle_help_command(ctx, msg, None))
    return ctx, sent


def _press(ctx, view, label, owner):
    """Press a help button as a user who is (or isn't) an owner."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    ctx.config.is_owner.return_value = owner
    button = next(b for b in view.children if b.label == label)
    inter = MagicMock()
    inter.response.edit_message = AsyncMock()
    inter.response.send_message = AsyncMock()
    asyncio.run(button.callback(inter))
    return inter


def _all_pages(is_owner):
    from utils.commands.help_handler import section_embed, sections
    return " ".join(f.value for s in sections(is_owner) for f in section_embed(s, is_owner).fields)


def test_help_documents_every_non_admin_command():
    """The old help omitted three dispatched aliases. Rendering from the table
    makes that impossible."""
    body = _all_pages(is_owner=False)
    for cmd in COMMANDS:
        if not cmd.owner_only:
            assert f"!{cmd.name}" in body, f"!{cmd.name} missing from help"


def test_help_hides_admin_commands_from_ordinary_users():
    from utils.commands.help_handler import ADMIN, sections
    body = _all_pages(is_owner=False)
    assert ADMIN not in sections(False)
    for cmd in COMMANDS:
        if cmd.owner_only:
            assert f"`!{cmd.name}`" not in body, f"!{cmd.name} shown to a non-owner"


def test_help_shows_admin_commands_to_owners():
    body = _all_pages(is_owner=True)
    assert "!reindex" in body and "!sysmon" in body


def test_help_is_one_short_landing_page_with_a_button_per_section():
    from utils.commands.help_handler import LABELS, sections
    _, sent = _help(is_owner=False)
    (embed, view), = sent
    assert len(embed) < 1500                               # not the old 45-command wall
    labels = [b.label for b in view.children]
    assert labels == ["Home"] + [LABELS[s][1] for s in sections(False)]


def test_a_section_button_swaps_the_page_in_place():
    ctx, sent = _help(is_owner=False)
    inter = _press(ctx, sent[0][1], "Music & art", owner=False)
    kwargs = inter.response.edit_message.call_args.kwargs
    assert "!music" in " ".join(f.value for f in kwargs["embed"].fields)
    pressed = next(b for b in kwargs["view"].children if b.label == "Music & art")
    assert pressed.style.name == "primary"


def test_admin_is_only_shown_to_an_owner_who_presses_it():
    ctx, sent = _help(is_owner=True)
    inter = _press(ctx, sent[0][1], "Admin", owner=False)  # someone else in the channel
    assert not inter.response.edit_message.called
    assert "!reindex" not in str(inter.response.send_message.call_args)
    inter = _press(ctx, sent[0][1], "Admin", owner=True)
    assert "!reindex" in " ".join(f.value for f in inter.response.edit_message.call_args.kwargs["embed"].fields)


def test_help_with_a_word_opens_that_command_or_section():
    _, sent = _help(is_owner=False, content="!help eam")       # an alias
    assert sent[0][0].title == "!skyking" and sent[0][1] is None
    _, sent = _help(is_owner=False, content="!help aethelgard")
    assert "Aethelgard" in sent[0][0].title and sent[0][1] is not None
    _, sent = _help(is_owner=False, content="!help nonsense")
    assert sent[0][0].title == "Not a command" and sent[1][1] is not None


@pytest.mark.parametrize("is_owner", [True, False])
def test_help_embed_stays_within_discord_limits(is_owner):
    """Discord rejects a field over 1024 chars, an embed over 6000, or a view
    of more than 25 buttons in 5 rows."""
    from utils.commands.help_handler import (command_embed, help_view, home_embed, section_embed,
                                             sections, HOME)
    pages = [home_embed(is_owner)] + [section_embed(s, is_owner) for s in sections(is_owner)]
    pages += [command_embed(c, is_owner) for c in COMMANDS]
    for embed in pages:
        for field in embed.fields:
            assert len(field.value) <= 1024, f"field '{field.name}' too long"
        assert len(embed) <= 6000 and len(embed.fields) <= 25
    for page in [HOME] + sections(is_owner):
        view = help_view(None, is_owner, page)
        assert len(view.children) <= 25 and max(b.row for b in view.children) <= 4


# ── Dispatch behaviour ───────────────────────────────────────────────

def test_a_failing_handler_does_not_fall_through_to_chat():
    """dispatch_command must still return True, or '!reindex --full' would be
    answered as if it were conversation."""
    import asyncio
    from unittest.mock import MagicMock

    async def boom(*_args):
        raise RuntimeError("handler exploded")

    sent = []

    async def send(content=None, embed=None, **_):
        sent.append(content if embed is None else embed.description)

    msg = MagicMock()
    msg.content = "!news"
    msg.author.name = "u"
    msg.channel.send = send

    original = registry.LOOKUP["!news"].handler
    try:
        registry.LOOKUP["!news"].handler = boom
        handled = asyncio.run(
            registry.dispatch_command(MagicMock(), msg, None, None)
        )
    finally:
        registry.LOOKUP["!news"].handler = original

    assert handled is True
    assert sent and "failed" in sent[0]


def test_non_command_is_not_handled():
    import asyncio
    from unittest.mock import MagicMock

    msg = MagicMock()
    msg.content = "hey kaia, what's up?"
    assert asyncio.run(
        registry.dispatch_command(MagicMock(), msg, None, None)
    ) is False

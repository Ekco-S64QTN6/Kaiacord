"""Forum identity links require an authored, unquoted, one-use proof."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


DISCORD_ID = "123456789012345678"
OTHER_DISCORD_ID = "223456789012345678"
FORUM_ID = 210090
CHALLENGE = "kaia-proof-" + ("a" * 40)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from utils.social.kaia_identities import IdentityRegistry

    monkeypatch.setattr(IdentityRegistry, "REGISTRY_PATH", tmp_path / "identity.json")
    return IdentityRegistry()


def test_pending_challenge_is_not_an_active_identity_mapping(registry):
    registry.begin_pending_forum_link(
        DISCORD_ID, FORUM_ID, CHALLENGE, expires_at=time.time() + 900
    )

    assert registry.get_discord_id(FORUM_ID) is None
    assert registry.get_forum_ids(DISCORD_ID) == []
    assert registry.pending_forum_link_challenge(DISCORD_ID, FORUM_ID) == CHALLENGE
    assert registry.pending_forum_link_challenge(OTHER_DISCORD_ID, FORUM_ID) is None


def test_only_exact_unexpired_pending_proof_activates_canonical_snowflake(registry):
    registry.begin_pending_forum_link(
        DISCORD_ID, FORUM_ID, CHALLENGE, expires_at=time.time() + 900
    )

    assert not registry.complete_pending_forum_link(DISCORD_ID, FORUM_ID, "wrong-token")
    assert registry.get_discord_id(FORUM_ID) is None

    assert registry.complete_pending_forum_link(DISCORD_ID, FORUM_ID, CHALLENGE)
    registry.set_display_name(DISCORD_ID, "Changed Nickname")

    assert registry.get_discord_id(FORUM_ID) == DISCORD_ID
    assert registry.get_forum_ids(DISCORD_ID) == [FORUM_ID]
    assert registry.describe_forum_user(FORUM_ID) == "Changed Nickname"
    assert registry.pending_forum_link_challenge(DISCORD_ID, FORUM_ID) is None


def test_pending_proof_expires_and_cannot_be_replayed(registry):
    registry.begin_pending_forum_link(
        DISCORD_ID, FORUM_ID, CHALLENGE, expires_at=time.time() - 1
    )
    assert registry.pending_forum_link_challenge(DISCORD_ID, FORUM_ID) is None
    assert not registry.complete_pending_forum_link(DISCORD_ID, FORUM_ID, CHALLENGE)
    assert registry.get_discord_id(FORUM_ID) is None


def test_conflicting_forum_owner_cannot_be_reassigned_by_a_new_challenge(registry):
    registry.link_discord_to_forum(DISCORD_ID, FORUM_ID)

    with pytest.raises(ValueError, match="already linked"):
        registry.begin_pending_forum_link(
            OTHER_DISCORD_ID, FORUM_ID, CHALLENGE, expires_at=time.time() + 900
        )
    with pytest.raises(ValueError, match="already linked"):
        registry.link_discord_to_forum(OTHER_DISCORD_ID, FORUM_ID)

    assert registry.get_discord_id(FORUM_ID) == DISCORD_ID
    assert registry.get_forum_ids(DISCORD_ID) == [FORUM_ID]
    assert registry.get_forum_ids(OTHER_DISCORD_ID) == []


def test_pending_request_for_a_forum_id_is_exclusive(registry):
    registry.begin_pending_forum_link(
        DISCORD_ID, FORUM_ID, CHALLENGE, expires_at=time.time() + 900
    )
    with pytest.raises(ValueError, match="pending proof request"):
        registry.begin_pending_forum_link(
            OTHER_DISCORD_ID, FORUM_ID, "another-challenge", expires_at=time.time() + 900
        )


def test_owner_unlink_removes_both_mapping_directions(registry):
    registry.link_discord_to_forum(DISCORD_ID, FORUM_ID)
    assert registry.unlink_forum_from_discord(DISCORD_ID, FORUM_ID)
    assert registry.get_discord_id(FORUM_ID) is None
    assert registry.get_forum_ids(DISCORD_ID) == []
    assert not registry.unlink_forum_from_discord(OTHER_DISCORD_ID, FORUM_ID)


def test_forum_public_post_verification_checks_author_and_unquoted_own_text(monkeypatch):
    from utils.social.kaia_forum import ForumClient

    client = object.__new__(ForumClient)
    client.scrape_user_post_history = AsyncMock(return_value=[
        {"thread_id": 101},
        {"thread_id": 202},
    ])
    client.scrape_thread = AsyncMock(side_effect=[
        {
            "posts": [
                # A different author quoting the token is not proof.
                SimpleNamespace(user_id=FORUM_ID + 1, own_text="quoted code: " + CHALLENGE),
            ]
        },
        {
            "posts": [
                # The target user quoting a challenge in a quote box is not proof.
                SimpleNamespace(
                    user_id=FORUM_ID,
                    own_text="I am quoting somebody else.",
                    content="Quoted: " + CHALLENGE,
                ),
                # Only an exact standalone line in their own text proves control.
                SimpleNamespace(
                    user_id=FORUM_ID,
                    own_text="Here is the requested code:\\n" + CHALLENGE + "\\nThanks.",
                    content="Here is the requested code: " + CHALLENGE,
                ),
            ]
        },
    ])
    monkeypatch.setattr("utils.social.kaia_forum.asyncio.sleep", AsyncMock())

    assert asyncio.run(client.verify_user_public_post(FORUM_ID, CHALLENGE))
    assert client.scrape_user_post_history.await_count == 1
    assert client.scrape_thread.await_args_list[0].args == (101,)
    assert client.scrape_thread.await_args_list[1].args == (202,)


def test_forum_public_post_verification_rejects_quoted_only_challenge(monkeypatch):
    from utils.social.kaia_forum import ForumClient

    client = object.__new__(ForumClient)
    client.scrape_user_post_history = AsyncMock(return_value=[{"thread_id": 101}])
    client.scrape_thread = AsyncMock(return_value={
        "posts": [
            SimpleNamespace(
                user_id=FORUM_ID,
                own_text="This is my comment.",
                content="Quoted: " + CHALLENGE,
            )
        ]
    })

    assert not asyncio.run(client.verify_user_public_post(FORUM_ID, CHALLENGE))


def test_link_handler_uses_numeric_snowflake_and_leaves_link_pending(monkeypatch, registry):
    import utils.commands.forum_handler as handler
    from utils.social import kaia_forum, kaia_identities

    monkeypatch.setattr(kaia_identities, "registry", registry)
    fake_client = SimpleNamespace(scrape_user_profile=AsyncMock(return_value={
        "user_id": FORUM_ID, "username": "Starkind",
    }))
    monkeypatch.setattr(kaia_forum, "get_forum_client", AsyncMock(return_value=fake_client))
    monkeypatch.setattr("secrets.token_urlsafe", lambda _n: CHALLENGE)

    author = SimpleNamespace(id=int(DISCORD_ID), name="OldName", display_name="NewName")
    channel = SimpleNamespace(send=AsyncMock())
    msg = SimpleNamespace(author=author, channel=channel)

    asyncio.run(handler._handle_link(SimpleNamespace(), msg, FORUM_ID))

    assert registry.get_discord_id(FORUM_ID) is None
    assert registry.get_forum_ids(DISCORD_ID) == []
    assert registry.pending_forum_link_challenge(DISCORD_ID, FORUM_ID) == CHALLENGE
    assert channel.send.await_count == 1


def test_verify_handler_activates_only_after_forum_client_confirms_authored_post(monkeypatch, registry):
    import utils.commands.forum_handler as handler
    from utils.social import kaia_forum, kaia_identities

    monkeypatch.setattr(kaia_identities, "registry", registry)
    registry.begin_pending_forum_link(
        DISCORD_ID, FORUM_ID, CHALLENGE, expires_at=time.time() + 900
    )
    fake_client = SimpleNamespace(
        scrape_user_profile=AsyncMock(return_value={"user_id": FORUM_ID, "username": "Starkind"}),
        verify_user_public_post=AsyncMock(return_value=False),
    )
    monkeypatch.setattr(kaia_forum, "get_forum_client", AsyncMock(return_value=fake_client))
    author = SimpleNamespace(id=int(DISCORD_ID), display_name="NewName")
    typing_cm = SimpleNamespace(
        __aenter__=AsyncMock(return_value=None),
        __aexit__=AsyncMock(return_value=False),
    )
    channel = SimpleNamespace(send=AsyncMock(), typing=lambda: typing_cm)
    msg = SimpleNamespace(author=author, channel=channel)

    asyncio.run(handler._handle_verify_link(SimpleNamespace(), msg, FORUM_ID))
    assert registry.get_discord_id(FORUM_ID) is None

    fake_client.verify_user_public_post.return_value = True
    asyncio.run(handler._handle_verify_link(SimpleNamespace(), msg, FORUM_ID))
    assert registry.get_discord_id(FORUM_ID) == DISCORD_ID
    assert registry.get_forum_ids(DISCORD_ID) == [FORUM_ID]
    assert registry.describe_forum_user(FORUM_ID) == "NewName"
    assert fake_client.verify_user_public_post.await_count == 2

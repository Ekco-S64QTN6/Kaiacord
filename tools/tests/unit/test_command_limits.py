"""Per-person limits on commands that fetch or file things."""


def test_forum_link_and_verify_share_a_cooldown():
    from utils.commands import forum_handler as fh
    fh._link_last.clear()
    assert fh._link_cooling(5) is False
    assert fh._link_cooling(5) is True
    assert fh._link_cooling(6) is False


def test_download_limit_counts_per_person_and_spares_the_owner(monkeypatch):
    import types
    from utils.commands import download_handler as dh
    from utils.infrastructure.system.yaml_config import config
    dh._added_today.clear()
    dh._added_day = ""
    monkeypatch.setattr(config, "get", lambda k, d=None: 2 if k == "download.max_per_user_per_day" else d)
    owner_ids = {"900"}
    monkeypatch.setattr(config, "is_owner", lambda n, dn, uid: uid in owner_ids)
    person = types.SimpleNamespace(author=types.SimpleNamespace(name="p", display_name="P", id=1))
    boss = types.SimpleNamespace(author=types.SimpleNamespace(name="o", display_name="O", id=900))
    assert dh._daily_limit_reached(person, "1") is False
    dh._note_added("1"); dh._note_added("1")
    assert dh._daily_limit_reached(person, "1") is True
    assert dh._daily_limit_reached(types.SimpleNamespace(author=types.SimpleNamespace(name="q", display_name="Q", id=2)), "2") is False
    for _ in range(5):
        dh._note_added("900")
    assert dh._daily_limit_reached(boss, "900") is False
    dh._added_today.clear()


def test_forum_review_buttons_answer_to_the_owner_unless_opened(monkeypatch):
    import asyncio
    import types
    from unittest.mock import AsyncMock
    from utils.infrastructure.system.yaml_config import config
    from utils.social.kaia_forum import ForumDraftReviewView
    view = ForumDraftReviewView.__new__(ForumDraftReviewView)
    sent = AsyncMock()
    who = types.SimpleNamespace(name="m", display_name="M", id=5)
    interaction = types.SimpleNamespace(user=who, response=types.SimpleNamespace(send_message=sent))
    monkeypatch.setattr(config, "is_owner", lambda n, d, uid: False)
    monkeypatch.setattr(config, "get", lambda k, d=None: d)
    assert asyncio.run(view.interaction_check(interaction)) is False and sent.await_count == 1
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "forum.review_owner_only" else d)
    assert asyncio.run(view.interaction_check(interaction)) is True

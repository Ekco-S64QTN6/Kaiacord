"""'kaia, who do you know?' answers with names, never profile contents."""
import asyncio
from types import SimpleNamespace

import utils.commands.profile_handler as ph


def _tree(tmp_path):
    for d in ("Ekco_177011971818782721", "Tenno_Henka_919782120308752425",
              "Kaia-Autonomous_channel_1462239450691145924",
              "forum_bob_123", "forum_alice_456", ".compacted_backup"):
        (tmp_path / d).mkdir()
    (tmp_path / "Ekco_177011971818782721" / "user_profile.md").write_text(
        "---\ngenerated: x\n---\n# INTERNAL MEMORY: Ekco\nsecret notes")
    return tmp_path


def test_names_only_and_forum_users_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "LOGS_DIR", _tree(tmp_path))
    names, forum = ph.get_known_users()
    assert names == ["Ekco", "Tenno Henka"]
    assert forum == 2


def test_the_reply_never_carries_a_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(ph, "LOGS_DIR", _tree(tmp_path))
    sent = []

    async def send(channel, text):
        sent.append(text)

    msg = SimpleNamespace(channel=None, author=SimpleNamespace(id=1, display_name="x"))
    handled = asyncio.run(ph.handle_profile_query(msg, "kaia who do you know", send, None, None))
    assert handled and len(sent) == 1
    assert "Ekco" in sent[0] and "2 from the project 1999 forums" in sent[0]
    assert "INTERNAL" not in sent[0] and "generated" not in sent[0] and "secret" not in sent[0]


def test_ordinary_messages_are_not_taken():
    assert not ph.is_user_list_query("kaia what do you know about pixel")
    assert ph.is_user_list_query("kaia list users")


def test_asked_as_a_reply_it_still_answers():
    quoted = "[REPLYING_TO]\nLune: " + "a long quoted message " * 10 + "\n\n[USER_MESSAGE]\nkaia who do you know"
    assert ph.is_user_list_query(quoted)

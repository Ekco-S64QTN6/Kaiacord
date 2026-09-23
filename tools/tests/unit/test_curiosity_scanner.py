"""The curiosity scanner quotes what the user said, from the user's own log."""
import os

from utils.core import curiosity_scanner as cs


def _logs(tmp_path, folder, text):
    d = tmp_path / "user_logs" / folder
    d.mkdir(parents=True)
    (d / "interactions_20260922.md").write_text(text, encoding="utf-8")
    return d


def test_the_discord_folder_wins_over_a_forum_folder_with_the_same_name(tmp_path):
    _logs(tmp_path, "forum_Ekco_251675", "x")
    chat = _logs(tmp_path, "Ekco_177011971818782721", "x")
    found = cs._find_user_log_dir("177011971818782721", "Ekco", str(tmp_path))
    assert found == str(chat)
    assert cs._find_user_log_dir("999", "Ekco", str(tmp_path)) == str(chat)
    assert cs._find_user_log_dir("999", "Nobody", str(tmp_path)) is None


def test_kaia_is_never_quoted_as_the_user():
    log = (
        "---\nsummary: \"\"\n---\n"
        "[2026-09-22 03:09:07] Ekco: status?\n"
        "[2026-09-22 03:09:07] Kaia: i'll try to remain grounded in the data.\n"
        "i'm planning to reread the logs.\n"
        "[2026-09-22 03:10:00] Ekco: nice [2026-09-22 03:10:00] Kaia: i'll check the cron job later.\n"
    )
    assert cs._find_unresolved_mentions(log) == []


def test_the_users_own_intent_is_found_most_recent_first():
    log = (
        "[2026-09-22 03:09:07] Ekco: i'll try the new driver tonight\n"
        "[2026-09-22 03:09:07] Kaia: good luck.\n"
        "[2026-09-22 04:00:00] Ekco: going to fix the fan bracket tomorrow\n"
        "and I'm working on the case mod too\n"
    )
    found = cs._find_unresolved_mentions(log)
    assert found[0] == "and I'm working on the case mod too"
    assert "i'll try the new driver tonight" in found


def test_recent_content_is_the_end_of_the_file(tmp_path):
    d = _logs(tmp_path, "Ekco_1", "old line\n" * 5000 + "newest line\n")
    content = cs._get_recent_log_content(str(d), days=3)
    assert content.rstrip().endswith("newest line")
    assert len(content) <= cs._MAX_LOG_CHARS

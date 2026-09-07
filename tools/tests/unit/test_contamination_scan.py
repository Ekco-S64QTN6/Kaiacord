"""The contamination scanner in kaia-tools.

Reported as: "Find contamination in kaia tools doesn't work and gives a error."

It crashed on every run, and the crash was hiding something worse — the menu
calls it "(scan only)" and passes --dry-run, but the script parsed no arguments
at all and would have rewritten user log files.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("tools/maintenance/clean_hallucinations.py")


def _run(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT.resolve()), *args],
                          capture_output=True, text=True, cwd=cwd)


@pytest.fixture
def logs(tmp_path):
    d = tmp_path / "user_logs" / "Someone_123"
    d.mkdir(parents=True)
    f = d / "interactions_20260829.md"
    f.write_text(
        "[2026-08-29 14:31:46] Someone: what did orwell mean by Eurasia anyway\n"
        "\n"
        "[2026-08-29 14:32:02] Kaia: the Pan-Pacific accords were signed in 1984\n"
        "\n"
        "[2026-08-29 14:33:00] Someone: that never happened\n",
        encoding="utf-8")
    return tmp_path / "user_logs", f


def test_it_runs_at_all(logs):
    """Every pattern carried an inline (?i) and was interpolated mid-expression;
    Python 3.11+ raises `global flags not at the start of the expression`."""
    r = _run("--dry-run", "--logs-dir", str(logs[0]))
    assert r.returncode == 0, r.stderr
    assert "global flags" not in r.stderr
    assert "Traceback" not in r.stderr


def test_scanning_changes_nothing_on_disk(logs):
    """The menu item says "scan only". It passed --dry-run to a script that
    parsed no arguments, so a working regex would have deleted lines."""
    logs_dir, f = logs
    before = f.read_text(encoding="utf-8")
    assert _run("--dry-run", "--logs-dir", str(logs_dir)).returncode == 0
    assert _run("--logs-dir", str(logs_dir)).returncode == 0      # no flag at all
    assert f.read_text(encoding="utf-8") == before


def test_it_finds_both_speakers_and_labels_them(logs):
    r = _run("--logs-dir", str(logs[0]))
    assert "line 1" in r.stdout and "line 3" in r.stdout
    assert "user, left alone" in r.stdout
    assert "1 from Kaia, 1 from users" in r.stdout


def test_apply_never_touches_a_user_line(logs):
    """The one real match in the live corpus is a user quoting a news article
    about Russia. Deleting a person's own words to tidy up the bot's mistakes
    is not what anyone asked for."""
    logs_dir, f = logs
    assert _run("--apply", "--logs-dir", str(logs_dir)).returncode == 0
    after = f.read_text(encoding="utf-8")
    assert "what did orwell mean by Eurasia" in after, "user line must survive"
    assert "Pan-Pacific accords" not in after, "Kaia's line should be removed"
    assert "that never happened" in after


def test_apply_writes_a_backup_first(logs):
    logs_dir, f = logs
    before = f.read_text(encoding="utf-8")
    _run("--apply", "--logs-dir", str(logs_dir))
    bak = f.with_suffix(f.suffix + ".bak")
    assert bak.exists() and bak.read_text(encoding="utf-8") == before


def test_patterns_are_case_insensitive_without_inline_flags(logs):
    r = _run("--pattern", "EURASIA", "--logs-dir", str(logs[0]))
    assert "line 1" in r.stdout, "should match regardless of case"
    assert r.returncode == 0


def test_a_missing_logs_dir_is_reported_not_crashed(tmp_path):
    r = _run("--logs-dir", str(tmp_path / "nope"))
    assert r.returncode == 1 and "No such directory" in r.stdout


def test_every_menu_invocation_says_what_it_means():
    """Each kaia-tools entry must pass a flag the script accepts, and the flag
    must match the label. The "Surgical Fix (APPLY)" entry passed *no* flag,
    which meant "delete" to the old script and "report" to the new one — so it
    would have silently done nothing.
    """
    menu = Path("scripts/kaia-tools.sh").read_text(encoding="utf-8")
    src = SCRIPT.read_text(encoding="utf-8")
    calls = [l.strip() for l in menu.splitlines() if "clean_hallucinations.py" in l]
    assert calls, "menu should still offer the scanner"

    for line in calls:
        flags = [w for w in line.split() if w.startswith("--")]
        assert flags, f"no flag, so the intent is ambiguous: {line}"
        for f in flags:
            assert f in src, f"{f} is not handled by the script"
        if "APPLY" in line:
            assert "--apply" in flags, f"APPLY entry must pass --apply: {line}"
        else:
            assert "--apply" not in flags, f"scan-only entry must not apply: {line}"

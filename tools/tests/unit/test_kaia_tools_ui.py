"""The kaia-tools presentation layer.

The tool rendered through whiptail, which an operator described as "some MS-DOS
installer from 1994". `ui_dialog` accepts whiptail's argument grammar unchanged
so the ~19 call sites did not move, and renders with fzf when it is available.

These tests drive the shell functions directly with a stubbed fzf, because the
thing most likely to break is the argument parsing between the two grammars.
"""
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path("scripts/kaia-tools.sh")
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _layer() -> str:
    """The presentation layer, lifted out of the script."""
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("# ── Presentation layer"))
    end = next(i for i, l in enumerate(lines) if l.startswith("confirm() {"))
    return "\n".join(lines[start:end])


def _run(body: str, tmp_path=None):
    prelude = textwrap.dedent("""
        set -uo pipefail
        term_cols(){ echo 80; }; term_rows(){ echo 30; }
        bot_running(){ return 0; }; ollama_running(){ return 0; }
    """)
    return subprocess.run(["bash", "-c", prelude + _layer() + "\n" + body],
                          capture_output=True, text=True)


def test_the_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_a_menu_returns_the_tag_not_the_label():
    """Call sites capture the result with whiptail's `3>&1 1>&2 2>&3` swap, so
    the answer must go to stderr while the UI goes to the terminal."""
    r = _run(r'''
        fzf() { cat >/dev/null; printf '4\tKnowledge Base\t'; }
        CHOICE=$(ui_dialog --title T --menu "p" 17 72 3 \
            "1" "System" "4" "Knowledge Base  (clean)" "q" "Quit" 3>&1 1>&2 2>&3)
        echo "TAG=$CHOICE"
    ''')
    assert "TAG=4" in r.stdout, r.stderr


def test_hints_become_a_separate_dim_column(tmp_path):
    """"Label  (hint)" is split so the hint can be dimmed rather than competing
    with the label. fzf's stdout is consumed by a command substitution, so the
    stub has to hand the rows back through a file."""
    out = tmp_path / "rows"
    r = _run(rf'''
        fzf() {{ sed 's/\x1b\[[0-9;]*m//g' > {out}; return 1; }}
        ui_dialog --title T --menu "p" 17 72 1 \
            "4" "Knowledge Base  (clean, sanitize, profiles)" 2>/dev/null || true
    ''')
    assert out.read_text().strip().split("\t") == [
        "4", "Knowledge Base", "clean, sanitize, profiles"], r.stderr


def test_a_label_without_a_hint_still_works(tmp_path):
    out = tmp_path / "rows"
    _run(rf'''
        fzf() {{ sed 's/\x1b\[[0-9;]*m//g' > {out}; return 1; }}
        ui_dialog --title T --menu "p" 17 72 1 "6" "News" 2>/dev/null || true
    ''')
    assert out.read_text().rstrip("\n").split("\t")[:2] == ["6", "News"]


def test_inputbox_arguments_are_parsed_including_the_default():
    r = _run(r'''
        _ui_input_fzf() { echo "T=[$1] P=[$2] D=[$3]"; }
        ui_dialog --title "Backfill" --inputbox "Pages to walk:" 9 66 "4"
    ''')
    assert 'T=[Backfill] P=[Pages to walk:] D=[4]' in r.stdout


def test_defaultno_preselects_the_safe_answer(tmp_path):
    """confirm_offline_rebuild passes --defaultno to guard a RAG wipe against a
    running bot. Whiptail honoured it; dropping it would make a stray Enter
    destructive."""
    out = tmp_path / "rows"
    def first_row():
        return out.read_text().splitlines()[0].split("\t")[1]

    _run(rf'''
        fzf() {{ sed 's/\x1b\[[0-9;]*m//g' > {out}; return 1; }}
        ui_dialog --title T --yesno "p" 10 65 2>/dev/null || true
    ''')
    assert first_row() == "Yes, continue"

    _run(rf'''
        fzf() {{ sed 's/\x1b\[[0-9;]*m//g' > {out}; return 1; }}
        ui_dialog --title T --yesno "p" 14 70 --defaultno 2>/dev/null || true
    ''')
    assert first_row() == "No, cancel"


def test_yesno_exit_status_drives_the_shell_conditionals():
    r = _run(r'''
        fzf() { cat >/dev/null; printf 'yes\tYes'; }
        ui_dialog --title T --yesno "p" 10 65 && echo ACCEPTED
        fzf() { cat >/dev/null; printf 'no\tNo'; }
        ui_dialog --title T --yesno "p" 10 65 || echo DECLINED
    ''')
    assert "ACCEPTED" in r.stdout and "DECLINED" in r.stdout


def test_an_aborted_menu_is_a_nonzero_exit():
    """Every call site ends with `|| return`, so Esc must not read as a choice."""
    r = _run(r'''
        fzf() { cat >/dev/null; return 130; }
        ui_dialog --title T --menu "p" 17 72 1 "1" "One" 2>/dev/null || echo ABORTED
    ''')
    assert "ABORTED" in r.stdout


def test_the_whiptail_fallback_gets_the_original_arguments(tmp_path):
    shim = tmp_path / "whiptail"
    shim.write_text('#!/usr/bin/env bash\nprintf "%s|" "$@" >&2\n', encoding="utf-8")
    shim.chmod(0o755)
    r = _run(rf'''
        export PATH="{tmp_path}:$PATH"
        KAIA_TOOLS_UI=whiptail
        ui_dialog --title "Backfill" --inputbox "Pages:" 9 66 "4"
    ''')
    assert r.stderr.strip("|").split("|") == [
        "--title", "Backfill", "--inputbox", "Pages:", "9", "66", "4"]


def test_the_banner_draws_a_closed_box():
    """A first version built the rule with `tr ' ' '─'`, which substitutes
    bytes — every character in the frame is multibyte, so it produced
    mojibake."""
    r = _run("ui_banner")
    plain = [l for l in r.stdout.splitlines() if l.strip()]
    stripped = [__import__("re").sub(r"\x1b\[[0-9;]*m", "", l) for l in plain]
    assert stripped[0].strip().startswith("╭") and stripped[0].strip().endswith("╮")
    assert stripped[-1].strip().startswith("╰") and stripped[-1].strip().endswith("╯")
    assert "�" not in r.stdout
    widths = {len(s.rstrip()) for s in (stripped[0], stripped[-1])}
    assert len(widths) == 1, f"frame edges disagree: {widths}"


def test_it_no_longer_hard_requires_whiptail():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "! command -v fzf" in src and "! command -v whiptail" in src
    assert "whiptail is required but not installed" not in src


def test_every_dialog_goes_through_the_layer():
    """One place decides how anything is drawn."""
    src = SCRIPT.read_text(encoding="utf-8")
    stray = [l.strip() for l in src.splitlines()
             if "whiptail --title" in l and "command whiptail" not in l]
    assert not stray, f"call sites bypassing ui_dialog: {stray}"

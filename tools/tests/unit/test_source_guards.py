"""Guards that can only be checked by reading the code they sit in.

These pin text, not behaviour: each one names the fix it protects, and fails if that
line is removed. Where a behavioural test became practical it moved to its own file."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_unprompted_records_before_cross_posting():
    src = (ROOT / "utils/core/unprompted.py").read_text(encoding="utf-8")
    speak = src[src.index("async def speak("):]
    assert speak.index("record(bot_state, source=source)") < speak.index("post_to_bluesky")


def test_a_dream_on_a_submitted_document_is_not_posted(tmp_path, monkeypatch):
    src = (ROOT / "utils/social/agent_boards.py").read_text(encoding="utf-8")
    assert 'Submitted by' in src


def test_capture_deaths_are_counted_in_a_window():
    src = (ROOT / "utils/audio/strudel_source.py").read_text(encoding="utf-8")
    assert "RESTART_FORGET_S" in src


def test_concurrent_temporaries_have_distinct_names():
    src = (ROOT / "utils/radio/spectrogram.py").read_text(encoding="utf-8")
    assert "threading.get_ident()" in src


def test_the_delete_logs_menu_takes_only_a_date():
    src = (ROOT / "scripts/kaia-tools.sh").read_text(encoding="utf-8")
    assert '[[ "$DATE" =~ ^[0-9]{8}$ ]]' in src


def test_the_booth_answers_400_to_a_field_that_is_not_a_number():
    src = (ROOT / "utils/audio/dj_dashboard.py").read_text(encoding="utf-8")
    assert "def _do_post(self)" in src and "except (TypeError, ValueError, OverflowError)" in src


def test_a_records_start_tears_down_whatever_it_built_before_play():
    src = (ROOT / "utils/audio/records.py").read_text(encoding="utf-8")
    start = src[src.index("async def _start_records("):]
    assert start.index("deck = None\n    try:") < start.index("deck = Deck(first")


def test_the_ebook_converter_cannot_hang_on_a_bad_file():
    src = (ROOT / "tools/maintenance/ebook_to_kb_md.py").read_text(encoding="utf-8")
    assert src.count("timeout=600") == 2


def test_the_convert_menu_takes_a_folder_name_not_a_path():
    src = (ROOT / "scripts/kaia-tools.sh").read_text(encoding="utf-8")
    assert '[[ "$DEST" =~ ^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$ ]]' in src

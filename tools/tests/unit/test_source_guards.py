"""Guards that can only be checked by reading the code they sit in.

These pin text, not behaviour: each one names the fix it protects, and fails if that
line is removed. Where a behavioural test became practical it moved to its own file."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_unprompted_records_before_cross_posting():
    src = (ROOT / "utils/core/unprompted.py").read_text(encoding="utf-8")
    speak = src[src.index("async def speak("):]
    assert speak.index("record(bot_state, source=source)") < speak.index("post_to_bluesky")


def test_the_delete_logs_menu_takes_only_a_date():
    src = (ROOT / "scripts/kaia-tools.sh").read_text(encoding="utf-8")
    assert '[[ "$DATE" =~ ^[0-9]{8}$ ]]' in src


def test_a_records_start_tears_down_whatever_it_built_before_play():
    src = (ROOT / "utils/audio/records.py").read_text(encoding="utf-8")
    start = src[src.index("async def _start_records("):]
    assert start.index("deck = None\n    try:") < start.index("deck = Deck(first")


def test_the_ebook_converter_cannot_hang_on_a_bad_file():
    """Both converters run under the bounded runner (wall clock, CPU, output);
    test_ingress_conversion_limits exercises it."""
    from tools.maintenance import ebook_to_kb_md as E
    src = (ROOT / "tools/maintenance/ebook_to_kb_md.py").read_text(encoding="utf-8")
    assert src.count("_run_bounded(") == 3            # the runner and its two callers
    assert "subprocess.run(" not in src.split("def _run_bounded")[1].split("def extract_text")[0]
    assert 0 < E.CONVERT_WALL_S <= 600 and 0 < E.CONVERT_CPU_S <= E.CONVERT_WALL_S


def test_the_convert_menu_takes_a_folder_name_not_a_path():
    src = (ROOT / "scripts/kaia-tools.sh").read_text(encoding="utf-8")
    assert '[[ "$DEST" =~ ^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$ ]]' in src

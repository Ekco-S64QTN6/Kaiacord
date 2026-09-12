"""The transcript format retrieval depends on.

`kb_cleanse_user_logs.py` asked a model to rewrite each log into a "clean
'User: ...' / 'Kaia: ...' pattern". It complied across 774 files and in doing
so removed the three things the retrieval layer runs on:

  * the `[YYYY-MM-DD HH:MM:SS] Name: ` marker ConversationTurnSplitter chunks
    on — without it a whole day is one blob and the indexer falls back to blind
    500-character windows;
  * the timestamp the indexer reads for recency, leaving filesystem mtime,
    which the rewrite had just set to the day it ran;
  * the speaker's name, which scopes a log to its user.
"""
import re
from pathlib import Path

import pytest

LOGS = Path("knowledge_base/user_logs")
MARKER = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] [^:]+: ", re.M)
PREAMBLE = re.compile(r"(here'?s the cleaned|adhering to your instructions|"
                      r"\*\*CLEANED LOG)", re.I)


def _discord_logs():
    if not LOGS.exists():
        pytest.skip("no corpus")
    return [f for f in LOGS.glob("*/interactions_*.md")
            if not f.parent.name.startswith("forum_")]


def test_most_transcripts_carry_turn_markers():
    """848 of 1,112 files had none, so 76% of the corpus was chunked blind."""
    files = _discord_logs()
    blobs = [f for f in files if not MARKER.search(f.read_text(encoding="utf-8", errors="replace"))]
    assert len(blobs) < len(files) * 0.2, \
        f"{len(blobs)}/{len(files)} transcripts have no turn markers"


def test_no_model_commentary_in_the_corpus():
    """The cleaner wrote its own preamble into the transcripts it rewrote."""
    bad = [f.name for f in LOGS.glob("*/*.md")
           if PREAMBLE.search(f.read_text(encoding="utf-8", errors="replace"))]
    assert not bad, f"model commentary still in the corpus: {bad[:5]}"


def test_speakers_are_named_not_generic():
    """"Ekco:" became "User:", so per-user retrieval isolation and attribution
    had nothing to key on."""
    files = _discord_logs()
    generic = [f.name for f in files
               if re.search(r"^User:", f.read_text(encoding="utf-8", errors="replace"), re.M)]
    assert len(generic) < 5, f"{len(generic)} transcripts still use a generic speaker"


def test_the_splitter_finds_turns_in_a_repaired_file():
    """End to end: a repaired transcript must actually chunk by turn."""
    from utils.core.kaia_rag_indexer import ConversationTurnSplitter
    files = [f for f in _discord_logs() if len(f.read_text(encoding="utf-8", errors="replace")) > 2000]
    if not files:
        pytest.skip("no substantial transcripts")
    sample = files[0].read_text(encoding="utf-8", errors="replace")
    parts = ConversationTurnSplitter._TURN_PATTERN.split(sample)
    assert (len(parts) - 1) // 2 >= 2, "splitter found no turns to chunk on"


def test_the_cleanser_cannot_flatten_a_log_again():
    """The prompt now forbids reformatting, and the result is checked."""
    src = Path("tools/maintenance/kb_cleanse_user_logs.py").read_text(encoding="utf-8")
    assert "NEVER change the line format" in src
    assert "Do not replace a" in src and "'User'" in src
    assert "rejected rewrite" in src, "no post-check guarding the rewrite"


def test_reconstructed_timestamps_are_declared():
    """Repaired files carry synthetic within-day times; nothing downstream
    should mistake them for original precision."""
    repaired = [f for f in _discord_logs()
                if "reconstructed_times: true" in f.read_text(encoding="utf-8", errors="replace")]
    assert repaired, "expected the repair to mark the files it rebuilt"


# ── The compaction tool ──────────────────────────────────────────────

def _tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "compact_user_logs", "tools/maintenance/compact_user_logs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_link_dump_becomes_a_citation():
    """A pasted URL followed by the scraped article, attributed to whoever
    pasted it. The title is what survives — a bare URL carries no topic for an
    embedding."""
    m = _tool()
    body = ("Kaia, https://home.cern/long-shutdown-3/\n\n"
            "CERN bids farewell to the LHC and enters Long Shutdown 3\n"
            "TOPIC:\nAccelerators\n" + "The LHC has pushed the frontiers of science. " * 30)
    out = m.compact_link_dump(body)
    assert "https://home.cern/long-shutdown-3/" in out
    assert "[shared link: CERN bids farewell to the LHC and enters Long Shutdown 3]" in out
    assert "pushed the frontiers" not in out
    assert len(out) < 300


def test_an_ordinary_message_with_a_link_is_untouched():
    """Someone writing at length around a link is not a scrape dump."""
    m = _tool()
    body = "have a look at https://example.com/x — i think the second half is wrong"
    assert m.compact_link_dump(body) == body


def test_navigation_debris_only_goes_where_a_link_was():
    """Short lines are normal speech; they are only debris next to a citation."""
    m = _tool()
    chat = "yeah\nlol\nRa willing"
    assert m.drop_fragments(chat) == chat
    scraped = "[shared link: A Title Goes Here]\nTOPIC:\nAccelerators\nthis sentence is real prose"
    out = m.drop_fragments(scraped)
    assert "TOPIC:" not in out and "Accelerators" not in out
    assert "this sentence is real prose" in out


def test_compaction_never_loses_a_turn_marker():
    """The format is the contract; a pass that breaks it must refuse."""
    m = _tool()
    text = ("[2026-06-29 00:00:00] Ekco: Kaia, https://home.cern/x\n\n"
            "CERN bids farewell to the LHC\nTOPIC:\n" + "body text. " * 100 +
            "\n\n[2026-06-29 00:01:00] Kaia: noted.\n")
    out, stats = m.compact_text(text)
    assert len(m.TURN_MARKER.findall(out)) == 2
    assert stats["link_dump"] == 1


def test_compaction_is_idempotent():
    m = _tool()
    text = ("[2026-06-29 00:00:00] Ekco: Kaia, https://home.cern/x\n\n"
            "CERN bids farewell to the LHC\n" + "body text. " * 100 + "\n")
    once, _ = m.compact_text(text)
    twice, stats = m.compact_text(once)
    assert twice == once and not stats


def test_kaias_own_turns_are_never_rewritten():
    m = _tool()
    text = ("[2026-06-29 00:01:00] Kaia: here is https://example.com/a and then "
            + "a long reflective answer. " * 60 + "\n")
    out, _ = m.compact_text(text)
    assert out == text


def test_the_menu_offers_the_deterministic_tool():
    from pathlib import Path
    menu = Path("scripts/kaia-tools.sh").read_text(encoding="utf-8")
    assert "compact_user_logs.py" in menu
    assert "LLM Log Cleaner" not in menu, "the destructive cleaner is still wired up"


# ── Monthly rollup and folder index ──────────────────────────────────

def _mod(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_rolled_month_keeps_every_turn():
    """Merging is only safe because each turn carries its own timestamp — the
    date lives in the line, not the filename."""
    m = _mod("tools/maintenance/rollup_user_logs.py", "rollup")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        u = Path(d) / "Ekco_1"
        u.mkdir()
        days = []
        for n in (1, 2, 3):
            f = u / f"interactions_2026030{n}.md"
            f.write_text(f"---\nsummary: \"\"\n---\n\n"
                         f"[2026-03-0{n} 10:00:00] Ekco: message {n}\n"
                         f"[2026-03-0{n} 10:01:00] Kaia: reply {n}\n",
                         encoding="utf-8")
            days.append(f)
        text, turns = m.build_archive("Ekco_1", "202603", days)
        assert turns == 6
        assert len(m.TURN_MARKER.findall(text)) == 6
        for n in (1, 2, 3):
            assert f"message {n}" in text and f"2026-03-0{n}" in text
        assert "archived: true" in text


def test_rollup_leaves_recent_days_alone():
    """Only today's file is ever appended to, but a month still open must not
    be merged or the archive is re-embedded on every message."""
    src = Path("tools/maintenance/rollup_user_logs.py").read_text(encoding="utf-8")
    assert "newest > cutoff" in src and "continue" in src
    assert "keep-days" in src


def test_an_archive_looks_as_old_as_its_contents():
    """kaia_proactive and kaia_dream decide what is new by mtime; a fresh
    archive would otherwise re-trigger a pass over months of old material."""
    src = Path("tools/maintenance/rollup_user_logs.py").read_text(encoding="utf-8")
    assert "os.utime(archive" in src


def test_archives_are_still_found_by_the_runtime_glob():
    """Everything that reads transcripts globs interactions_*.md."""
    archives = list(LOGS.glob("*/interactions_*_archive.md"))
    if not archives:
        pytest.skip("no archives yet")
    for a in archives[:3]:
        assert a.name.startswith("interactions_") and a.name.endswith(".md")


def test_each_active_user_folder_has_a_readable_index():
    idx = _mod("tools/maintenance/build_user_folder_index.py", "folderidx")
    for d in LOGS.iterdir():
        if not d.is_dir() or d.name.startswith("forum_"):
            continue
        if not any(d.glob("interactions_*.md")):
            continue
        readme = d / "README.md"
        assert readme.exists(), f"{d.name} has no README.md"
        text = readme.read_text(encoding="utf-8")
        assert idx.display_name(d.name) in text
        assert "Turns on record" in text and "## Files" in text


def test_the_index_reports_topics_not_punctuation():
    """URLs and citation words ranked as the user's main interests before the
    content words were separated out."""
    readme = LOGS / "Ekco_177011971818782721" / "README.md"
    if not readme.exists():
        pytest.skip("no index")
    body = readme.read_text(encoding="utf-8").split("## What they talk about")[1]
    topics = next(l for l in body.splitlines() if l.startswith("> "))
    for junk in ("https", "shared", "link", "ekco"):
        assert junk not in topics.split(" · "), f"{junk!r} is not a topic"


# ── Re-running a corpus pass must not cost anything ──────────────────

def test_compaction_is_idempotent_and_keeps_the_citation():
    """A second run used to delete the page title the first run recovered.

    compact_link_dump truncates the turn at the URL and appends
    `[shared link: <title>]`. When the text before the URL is itself over
    MIN_DUMP, the turn still qualifies on a re-run — and by then the line after
    the URL is that citation, which link_title() skips as a bracket line. The
    turn came back without it. Both the menu item and the standalone tool are
    run more than once, so this had to be a no-op, not merely stable-ish.
    """
    from tools.maintenance.compact_user_logs import compact_link_dump

    body = ("i keep coming back to this one, it is the clearest thing "
            "anyone has written on the subject. " * 12 +
            "\nhttps://example.com/the-quiet-collapse\n"
            "The Quiet Collapse of Prediction Markets\n"
            "Share:\nnav\nsome real article body text follows here\n")

    once = compact_link_dump(body)
    assert "[shared link: The Quiet Collapse of Prediction Markets]" in once

    twice = compact_link_dump(once)
    assert twice == once, "second pass changed an already-compacted turn"
    assert "[shared link:" in twice, "the re-run dropped the recovered title"


def test_the_standalone_tool_carries_the_same_guard():
    """compact_link_dumps.py predates the consolidated pass and is still
    runnable by hand; it must not be the lossy copy."""
    from tools.maintenance.compact_link_dumps import compact_turn

    body = ("this is the piece i mentioned, worth the read in full. " * 18 +
            "\nhttps://example.com/piece\n"
            "A Title That Should Survive Both Passes\nmore body\n")
    once, changed = compact_turn(body)
    assert changed and "[shared link:" in once
    twice, changed_again = compact_turn(once)
    assert not changed_again, "an already-compacted turn was reported as changed"
    assert twice == once

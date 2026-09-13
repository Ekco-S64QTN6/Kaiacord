"""Who said what in a recap.

The operator ran the verbose status recap and it credited a link to the wrong
person: Starkind posted a fractal URL and wrote "forwarding the url to @Ekco he
likes fractals", and the recap reported that Ekco had shared it.

Nothing was hallucinated. The chunk reached the prompt with no speaker on it, so
the only name in the text won.
"""
import pytest

from utils.core.context_optimizer import ContextOptimizer
from utils.core.rag_utils import speaker_from_log_path


STARKIND_LOG = ("knowledge_base/user_logs/Starkind_519557167779676160/"
                "interactions_20260912.md")


# ── The speaker is the directory, never the filename ──────────────────

@pytest.mark.parametrize("path,expected", [
    (STARKIND_LOG, "Starkind"),
    ("knowledge_base/user_logs/Tenno_Henka_919782120308752425/interactions_202608_archive.md",
     "Tenno Henka"),
    ("./knowledge_base/user_logs/Ekco_177011971818782721/user_profile.md", "Ekco"),
    ("knowledge_base/books/dune.md", ""),
    ("", ""),
])
def test_the_owning_folder_identifies_the_speaker(path, expected):
    """Every user's daily file is named `interactions_<date>.md`, so a basename
    is not an identity — the recap labelled its nodes with one and they arrived
    indistinguishable."""
    assert speaker_from_log_path(path) == expected


def test_a_recap_node_without_user_name_is_still_attributed():
    """`search_recent_events` rebuilt its result metadata from scratch with only
    source_type/file_path/retrieval_method, dropping the `user_name` the indexer
    had set — and `user_name` is the field this label is built from."""
    node = {
        "content": ("[2026-09-12 18:23:52] Starkind: here's the url\n"
                    "forwarding the url to @Ekco he likes fractals"),
        "metadata": {"source_type": "user_logs", "file_path": STARKIND_LOG,
                     "retrieval_method": "fallback"},
    }
    out = ContextOptimizer().optimize_context(
        "general", "persona", [node], [], "RECAP_QUERY", "what happened today")
    line = next((l for l in out["rag"].split("\n") if "CONVERSATION HISTORY" in l), "")
    assert "STARKIND" in line, f"speaker missing from attribution: {line!r}"
    assert "EKCO" not in line, "attributed to the person merely mentioned in the text"


def test_the_recap_path_carries_the_speaker_forward():
    """Fixed at the source as well as in the optimizer, so provenance and any
    other consumer of these nodes sees it too."""
    import inspect
    from utils.core.kaia_rag_query import RAGQueryMixin
    src = inspect.getsource(RAGQueryMixin.search_recent_events)
    assert src.count("speaker_from_log_path") >= 4, (
        "both the scored and fallback branches must set user_name and label")
    assert '"user_name"' in src


# ── Date provenance ───────────────────────────────────────────────────

@pytest.mark.parametrize("path,expected", [
    # The bug: an unanchored search over the whole path matched inside the
    # 19-digit Discord id (5195-57-16), raised ValueError on month 57, and
    # returned "" — so no user-log chunk ever carried a date.
    (STARKIND_LOG, "Sep 12"),
    ("knowledge_base/user_logs/Tenno_Henka_919782120308752425/interactions_202608_archive.md",
     "Aug 2026"),
    ("knowledge_base/user_logs/Ekco_177011971818782721/user_profile.md", ""),
    ("knowledge_base/books/dune.md", ""),
])
def test_the_date_comes_from_the_filename_not_the_discord_id(path, expected):
    assert ContextOptimizer._extract_date_from_path(path) == expected


def test_a_long_digit_run_alone_yields_no_date():
    """Any 19-digit id contains plausible-looking dates; none of them are dates."""
    assert ContextOptimizer._extract_date_from_path(
        "knowledge_base/user_logs/Someone_519557167779676160/notes.md") == ""


def test_both_speaker_and_date_reach_the_prompt():
    node = {
        "content": "[2026-09-12 18:23:52] Starkind: something happened",
        "metadata": {"source_type": "user_logs", "file_path": STARKIND_LOG},
    }
    out = ContextOptimizer().optimize_context(
        "general", "persona", [node], [], "RECAP_QUERY", "what happened")
    line = next(l for l in out["rag"].split("\n") if "CONVERSATION HISTORY" in l)
    assert "STARKIND" in line and "Sep 12" in line, line

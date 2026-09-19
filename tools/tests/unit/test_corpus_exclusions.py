"""What may and may not enter the RAG index.

A September 2026 audit of `knowledge_base/` found two kinds of material being
indexed that should never have been:

  * `knowledge_base/.test/` — 101 fixture files the suite's own corpus
    isolation had put there, walked into the production `logs` index as 101
    retrievable nodes. Their content is memory-injection fixtures:
    "User (TestUser): Remember this: …" / "Kaia: Logged it. I'll remember that."
  * `user_logs/forum_*/` bulk — post_history.md at 2,229K and raw
    interactions_*.md at 1,419K, against 129K of actual profiles, all landing
    in the same `logs` index as her Discord conversation history.
"""
import inspect
import os

from utils.core.kaia_rag_indexer import RAGIndexerMixin

SCAN = inspect.getsource(RAGIndexerMixin._scan_for_new_files) \
    if hasattr(RAGIndexerMixin, "_scan_for_new_files") else inspect.getsource(RAGIndexerMixin)
PRUNE = inspect.getsource(RAGIndexerMixin._prune_deleted_files)


# The indexer's own predicate, not a copy of it. A mirror in the test file can
# agree with itself while the code drifts — which is how three of these tests
# went on passing by matching substrings in the scanner's source after the rule
# had moved elsewhere.
_excluded = RAGIndexerMixin._is_excluded_path


def test_test_fixtures_are_not_indexed():
    assert _excluded("knowledge_base/.test/user_logs/TestUser_123456789/injected_1.txt")


def test_quarantine_is_not_indexed():
    assert _excluded("knowledge_base/_quarantine/whatever.md")
    assert _excluded("knowledge_base/_quarantine/corrupt_files/broken.md")
    assert _excluded("knowledge_base/_quarantine/dreams/transcript/x.md")


def test_the_backup_directories_are_not_indexed():
    """`.compacted_backup` held 474 files — the raw forum post histories that
    `compact_forum_profiles` had just replaced — and the log shows them being
    re-indexed one by one. Indexing a backup of superseded content gives her the
    summary and everything it summarised, which is what compaction exists to
    prevent. Same for the reflections `consolidate_dreams` folds away."""
    assert _excluded("knowledge_base/.compacted_backup/forum_Ekco_251675/post_history.md")
    assert _excluded("knowledge_base/.dream_archive/books/dream_20260208_034713_x.md")


def test_the_staging_area_is_not_indexed():
    """`_ingress` being excluded is what makes !download and !youtube safe to
    leave open to every user."""
    assert _excluded("knowledge_base/_ingress/whatever.md")


def test_the_real_corpus_is_still_indexed():
    """An exclusion rule that is too broad fails silently — the corpus simply
    gets smaller. Assert the folders that must survive it."""
    for keep in (
        "knowledge_base/books/Book - Neuromancer by William Gibson.md",
        "knowledge_base/documents/AI - Cognitive Architectures.md",
        "knowledge_base/news/daily/2026-09-19.md",
        "knowledge_base/news/tech_updates/x.md",
        "knowledge_base/wiki/Enchanter.md",
        "knowledge_base/troubleshooting/Troubleshooting_Crashing.md",
        "knowledge_base/transcripts/AI - Claude Opus Discussion.md",
        "knowledge_base/runtime/snapshots/snap_2026.md",
        "knowledge_base/kaia_dreams/consolidated/books/Snow_Crash.md",
        "knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260919.md",
    ):
        assert not _excluded(keep), f"{keep} would be dropped from the index"


def test_forum_bulk_is_excluded_but_the_profile_survives():
    """The profile is the cheat sheet the forum reply path wants; the complete
    post history is the part that drowned her Discord history."""
    assert _excluded("knowledge_base/user_logs/forum_BradZax_315418/post_history.md")
    assert _excluded("knowledge_base/user_logs/forum_BradZax_315418/interactions_20260907.md")
    assert not _excluded("knowledge_base/user_logs/forum_BradZax_315418/user_profile.md")


def test_discord_user_logs_are_untouched():
    """Only `forum_` directories are affected."""
    assert not _excluded(
        "knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260914.md")
    assert not _excluded(
        "knowledge_base/user_logs/Tenno_Henka_919782120308752425/interactions_20260914.md")


def test_the_scan_and_the_prune_apply_the_same_rule():
    """Both ends must consult one predicate.

    An exclusion that lives only in the scanner stops new files being *added*
    and does nothing about the ones indexed before it existed — the prune pass
    removed an entry only when its file had vanished from disk. Adding the
    dot-directory rule to the scan alone left 475 `.compacted_backup` entries in
    the manifest: the raw forum post histories compaction had replaced, still
    retrievable beside the profiles that superseded them.
    """
    assert "_is_excluded_path" in SCAN, "the scan no longer uses the shared rule"
    assert "_is_excluded_path" in PRUNE, (
        "the prune pass no longer uses the shared rule, so anything already "
        "indexed under an old rule will stay indexed forever"
    )


def test_a_forum_directory_keeps_only_its_profile():
    assert _excluded("knowledge_base/user_logs/forum_BradZax_315418/post_history.md")
    assert not _excluded("knowledge_base/user_logs/forum_BradZax_315418/user_profile.md")


def test_ingress_and_forum_posts_stay_excluded():
    """Pre-existing exclusions must survive the change."""
    assert _excluded("knowledge_base/_ingress/pending.md")
    assert _excluded("knowledge_base/forum_posts/thread_123_something.md")

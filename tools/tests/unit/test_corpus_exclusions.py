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


def _excluded(path: str) -> bool:
    """Mirror of the indexer's rule, for asserting on concrete paths.

    Any dot-directory, not just `.test`: that named exclusion left
    `.compacted_backup` and `.dream_archive` — the originals that compaction and
    consolidation had just superseded — being walked into the index.
    """
    n = path.replace("\\", "/")
    if any(part.startswith(".") and part not in (".", "..") for part in n.split("/")):
        return True
    return ("/_quarantine" in n or "/_ingress" in n or "forum_posts" in n
            or ("/user_logs/forum_" in n and os.path.basename(n) != "user_profile.md"))


def test_test_fixtures_are_not_indexed():
    assert 'part.startswith(".")' in SCAN, "dot-directories are walked into the index"
    assert "/.test/" in PRUNE, "already-indexed test fixtures are never pruned"
    assert _excluded("knowledge_base/.test/user_logs/TestUser_123456789/injected_1.txt")


def test_quarantine_is_not_indexed():
    assert "/_quarantine" in SCAN
    assert "/_quarantine/" in PRUNE, "already-indexed quarantined files are never pruned"
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


def test_the_indexer_implements_that_rule():
    assert "/user_logs/forum_" in SCAN, "forum user dirs are not special-cased on scan"
    assert 'user_profile.md' in SCAN, "the profile exception is missing"
    assert "/user_logs/forum_" in PRUNE, "existing forum bulk is never pruned"


def test_ingress_and_forum_posts_stay_excluded():
    """Pre-existing exclusions must survive the change."""
    assert "_ingress" in SCAN
    assert "forum_posts" in SCAN
    assert _excluded("knowledge_base/forum_posts/thread_123_something.md")

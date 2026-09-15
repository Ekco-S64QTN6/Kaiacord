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
    """Mirror of the indexer's rule, for asserting on concrete paths."""
    n = path.replace("\\", "/")
    return ("/.test/" in n or "/quarantine/" in n or "forum_posts" in n
            or ("/user_logs/forum_" in n and os.path.basename(n) != "user_profile.md"))


def test_test_fixtures_are_not_indexed():
    assert "/.test" in SCAN, "the .test corpus is still walked into the index"
    assert "/.test/" in PRUNE, "already-indexed test fixtures are never pruned"
    assert _excluded("knowledge_base/.test/user_logs/TestUser_123456789/injected_1.txt")


def test_quarantine_is_not_indexed():
    assert "/quarantine" in SCAN
    assert _excluded("knowledge_base/quarantine/whatever.md")


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

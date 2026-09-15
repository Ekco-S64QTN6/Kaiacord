"""Compaction must not reopen the re-scrape gate.

`scrape_active_users` decides whether to spend 20 post pages and 10 thread
pages on a user by comparing the site's current `total_posts` against a
watermark it recorded last time. That watermark lived only in
`post_history.md` — which `compact_forum_profiles.py --prune` deletes, since it
is hundreds of KB of raw posts that nothing reads and nothing indexes.

Deleting it without carrying the number forward would mean the gate never fires
again: every cycle re-downloads everything and rebuilds exactly the files that
were just removed. The watermark is therefore read from the history file *or*
the profile.
"""
from pathlib import Path

import pytest

from utils.social.kaia_forum import (
    _is_synthesised_profile, _recorded_total_posts, _watermark_covers,
)

PROFILE = (
    '---\n'
    'document_type: "User Personality Profile"\n'
    'platform: vbulletin\n'
    'compacted_from: 8\n'
    'total_posts: 1274\n'
    'user_id: 122962\n'
    '---\n\n# INTERNAL MEMORY: entruil\n'
)
HISTORY = '---\nusername: "entruil"\nuser_id: 122962\ntotal_posts: 1274\n---\n\nposts...\n'


@pytest.fixture
def user_dir(tmp_path):
    (tmp_path / "user_profile.md").write_text(PROFILE, encoding="utf-8")
    (tmp_path / "post_history.md").write_text(HISTORY, encoding="utf-8")
    return tmp_path


def test_watermark_is_read_from_either_file(user_dir):
    assert _recorded_total_posts(user_dir / "post_history.md") == 1274
    assert _recorded_total_posts(user_dir / "user_profile.md") == 1274


def test_an_unchanged_total_still_skips_after_the_history_is_pruned(user_dir):
    history = user_dir / "post_history.md"
    profile = user_dir / "user_profile.md"
    history.unlink()                                  # what --prune does
    assert _watermark_covers(1274, history, profile), \
        "compaction reopened the gate: the user would be fully re-scraped"


def test_new_posts_still_trigger_a_scrape(user_dir):
    """She must keep walking the forums for genuinely new material."""
    history = user_dir / "post_history.md"
    profile = user_dir / "user_profile.md"
    history.unlink()
    assert not _watermark_covers(1286, history, profile), \
        "twelve new posts failed to trigger a re-scrape"


def test_a_user_with_no_watermark_anywhere_is_scraped(tmp_path):
    """First contact: nothing recorded, so the expensive pass must run."""
    assert not _watermark_covers(500, tmp_path / "post_history.md",
                                 tmp_path / "user_profile.md")


def test_a_compacted_profile_still_counts_as_synthesised(user_dir):
    """Otherwise the separate 1-hour profile cooldown stops working and she
    re-scrapes profiles far more often than intended."""
    assert _is_synthesised_profile(user_dir / "user_profile.md")


def test_the_compactor_carries_the_watermark_and_refuses_to_prune_without_it():
    import inspect
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "cfp", "tools/maintenance/compact_forum_profiles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    src = inspect.getsource(module)
    assert "def read_watermark" in src
    assert "total_posts: {total_posts}" in src, "watermark not written to the profile"
    assert "NOT pruned" in src, "prunes even when the watermark could not be carried"

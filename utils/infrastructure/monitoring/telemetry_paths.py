"""One place that decides where telemetry is written.

Production telemetry — anything the dashboard, `!sysmon` or a later audit reads
back as a record of what Kaia did — must never contain output from the test
suite. Mock objects and `test-model` traces read back as production errors, and
a counter filled with fixtures is reported to the operator as a real figure.

Every writer that hardcodes its own path has to be fixed separately, so this
module is the single decision point: call `telemetry_path()` and get a
test-suffixed path under pytest and the real one otherwise.

`test_telemetry_isolation.py` asserts that every file the dashboard reads is
routed through here.
"""
from __future__ import annotations

import os
import sys

#: Files the dashboard, !sysmon or an audit reads back as a record of
#: production behaviour. Adding a metric source means adding it here.
DASHBOARD_SOURCES = frozenset({
    "memory/hallucination_log.jsonl",
    "memory/stats.json",
    "memory/generation_log.jsonl",
    "memory/security_dogtag_replay.jsonl",
    "memory/forum_moderation_log.jsonl",
    "logs/kaiacord.log",
})


def is_test_run() -> bool:
    """True when running under pytest.

    Checked at call time rather than import time: a module imported before the
    test session begins would otherwise cache the wrong answer.
    """
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def telemetry_path(path: str) -> str:
    """Resolve a telemetry path, redirecting to a test file under pytest.

    `memory/x.jsonl` becomes `memory/x.test.jsonl`. The suffix goes before the
    extension so the file keeps its type and tooling still recognises it.

    An explicit `KAIACORD_TELEMETRY_SUFFIX` overrides the decision, which is
    what the isolation tests use to prove redirection happens without having to
    fake a pytest session.
    """
    override = os.getenv("KAIACORD_TELEMETRY_SUFFIX")
    if override is not None:
        suffix = override
    elif is_test_run():
        suffix = ".test"
    else:
        return path

    if not suffix:
        return path
    root, ext = os.path.splitext(path)
    return f"{root}{suffix}{ext}"


# The same problem, one layer out. `!remember` writes a per-user file under
# knowledge_base/user_logs, and the suite exercises that path — so
# `knowledge_base/user_logs/TestUser_123456789/` had accumulated ~170
# `injected_*.txt` files, all of them fixtures, all of them indexed into the
# production RAG corpus and retrievable in a real conversation.
#
# Third instance of this failure after logs/kaiacord.log and
# hallucination_log.jsonl, and the reason this module exists.
TEST_CORPUS_SUBDIR = ".test"


def corpus_dir(knowledge_base_dir: str) -> str:
    """Where corpus writes go — a test subdirectory under pytest.

    Reads are deliberately unaffected: a test that writes then reads its own
    file still works, and nothing under `.test/` is indexed for production
    because the indexer skips dot-directories.
    """
    if is_test_run():
        return os.path.join(knowledge_base_dir, TEST_CORPUS_SUBDIR)
    return knowledge_base_dir


# `KaiaRAG` defaults to `./memory/rag_storage` and the suite constructs one, so
# without redirection every `pytest` run opens the *live* index and writes its
# empty fixture state over the running bot's `file_manifest.json`.
#
# The bot keeps the manifest in memory and restores it on its next save, so the
# damage is bounded — a restart inside that window re-indexes the whole corpus
# from scratch instead of incrementally. `reindex_rag.py` refuses to touch this
# directory while the bot is running for the same reason.
def persist_dir(path: str = "./memory/rag_storage") -> str:
    """Where RAG indices and the manifest live — a sibling directory under pytest."""
    if is_test_run():
        return f"{path.rstrip('/')}.test"
    return path

"""One place that decides where telemetry is written.

Production telemetry — anything the dashboard, `!sysmon` or a later audit reads
back as a record of what Kaia did — must never contain output from the test
suite. This has now gone wrong twice:

  * `logs/kaiacord.log` (fixed Phase 67 in `UnifiedLogger._resolve_log_file`).
    Mock objects and `test-model` traces read back as production ERRORs and
    cost real time to rule out during a log review.
  * `memory/hallucination_log.jsonl` (fixed Phase 80). Every one of its 368
    entries was a unit-test fixture, and `!sysmon` had been reporting that
    count as "hallucinations in the last 24h" — a figure that was 100% noise.

Both writers hardcoded their own path, so fixing one did nothing for the other.
This module is the single decision point: a writer calls `telemetry_path()` and
gets a test-suffixed path under pytest and the real one otherwise.

`test_telemetry_isolation.py` asserts that every file the dashboard reads is
routed through here, so a third instance cannot be introduced quietly.
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

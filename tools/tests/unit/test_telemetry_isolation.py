"""Test runs must never write into production telemetry.

This has gone wrong twice, in two different files, each of which hardcoded its
own path so fixing one did nothing for the other:

  * `logs/kaiacord.log` (Phase 67) — mock objects and `test-model` traces read
    back as production ERRORs during a log review.
  * `memory/hallucination_log.jsonl` (Phase 80) — **all 368 entries** were unit
    test fixtures, and `!sysmon` reported that count as "hallucinations in the
    last 24h".

`telemetry_paths.telemetry_path()` is now the single decision point. These
tests exist so a third instance cannot be introduced quietly.
"""
import ast
import io
import os
import pathlib
import re

import pytest

from utils.infrastructure.monitoring.telemetry_paths import (
    DASHBOARD_SOURCES,
    is_test_run,
    telemetry_path,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


# ── The resolver ─────────────────────────────────────────────────────

def test_pytest_is_detected():
    """These tests are themselves running under pytest."""
    assert is_test_run() is True


@pytest.mark.parametrize("source", sorted(DASHBOARD_SOURCES))
def test_every_dashboard_source_redirects_under_test(source):
    resolved = telemetry_path(source)
    assert resolved != source, f"{source} would be written during a test run"
    assert ".test" in resolved


def test_redirection_preserves_the_extension():
    """Tooling keys off the extension; the suffix goes before it."""
    assert telemetry_path("memory/x.jsonl") == "memory/x.test.jsonl"
    assert telemetry_path("logs/y.log") == "logs/y.test.log"
    assert telemetry_path("memory/z.json") == "memory/z.test.json"


def test_production_path_is_returned_when_not_testing(monkeypatch):
    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", "")
    assert telemetry_path("memory/stats.json") == "memory/stats.json"


def test_explicit_suffix_overrides_detection(monkeypatch):
    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", ".probe")
    assert telemetry_path("memory/stats.json") == "memory/stats.probe.json"


def test_nested_paths_are_handled():
    assert telemetry_path("memory/a/b/c.jsonl").endswith("c.test.jsonl")


# ── The writers ──────────────────────────────────────────────────────

# Modules that read a telemetry path but never write it.
READERS = {
    "utils/commands/sysmon_handler.py",
    "utils/infrastructure/system/dashboard_manager.py",
    "utils/infrastructure/monitoring/stats_poller.py",
    "utils/commands/scores_handler.py",
    "utils/commands/memory_handler.py",
    "utils/infrastructure/monitoring/telemetry_paths.py",
    "utils/infrastructure/logging/unified_logging.py",   # has its own resolver
}


def _source_files():
    for path in sorted((REPO / "utils").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in READERS or "__pycache__" in rel:
            continue
        yield rel, io.open(path, encoding="utf-8").read()


def _docstring_lines(tree):
    """Line numbers occupied by docstrings — prose, not code."""
    lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            d = body[0]
            lines.update(range(d.lineno, (d.end_lineno or d.lineno) + 1))
    return lines


@pytest.mark.parametrize("source", sorted(DASHBOARD_SOURCES))
def test_no_writer_hardcodes_a_dashboard_source(source):
    """A literal path outside telemetry_path() is how both regressions happened.

    Only *string literals in code* count. A docstring naming the file is
    documentation, and the earlier version of this test flagged three of them.
    """
    offenders = []
    for rel, text in _source_files():
        if source.split("/")[-1] not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        doc_lines = _docstring_lines(tree)
        code_lines = text.splitlines()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if source not in node.value and not node.value.endswith(source.split("/")[-1]):
                continue
            if node.lineno in doc_lines:
                continue
            line = code_lines[node.lineno - 1]
            if "telemetry_path" in line:
                continue
            offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        f"{source} appears as a literal outside telemetry_path() at {offenders}. "
        "Route it through telemetry_paths.telemetry_path so a test run cannot "
        "write to it."
    )


def test_dashboard_sources_all_exist_or_are_creatable():
    """A source named here but never written is a stale entry."""
    for src in DASHBOARD_SOURCES:
        parent = REPO / pathlib.Path(src).parent
        assert parent.exists(), f"{src}: {parent} does not exist"


# ── The live files ───────────────────────────────────────────────────

def test_this_run_did_not_touch_production_telemetry():
    """The whole point, asserted directly."""
    for src in DASHBOARD_SOURCES:
        assert telemetry_path(src) != src


# ── The corpus, not just telemetry ───────────────────────────────────

def test_corpus_writes_are_redirected_under_test():
    """`!remember` writes a per-user file into knowledge_base/user_logs, and the
    suite exercises that path — so TestUser_123456789/ had accumulated ~170
    `injected_*.txt` fixtures, indexed into the production RAG corpus and
    retrievable in a real conversation. Third instance of this failure after
    logs/kaiacord.log and hallucination_log.jsonl."""
    from utils.infrastructure.monitoring.telemetry_paths import corpus_dir
    assert corpus_dir("./knowledge_base").endswith(".test")


def test_the_persistence_layer_uses_the_redirect():
    import ast
    from pathlib import Path
    src = Path("utils/core/kaia_rag_persistence.py").read_text(encoding="utf-8")
    assert "corpus_dir(self.knowledge_base_dir)" in src
    tree = ast.parse(src)
    raw = [n for n in ast.walk(tree)
           if isinstance(n, ast.Attribute) and n.attr == "knowledge_base_dir"]
    # Every use must be wrapped; a bare one is a new write path that escapes.
    assert src.count("self.knowledge_base_dir") == src.count("corpus_dir(self.knowledge_base_dir)"), \
        "a knowledge_base_dir use is not routed through corpus_dir"


def test_no_test_fixtures_remain_in_the_production_corpus():
    from pathlib import Path
    logs = Path("knowledge_base/user_logs")
    if not logs.exists():
        pytest.skip("no corpus")
    strays = [d.name for d in logs.iterdir()
              if d.is_dir() and d.name.lower().startswith("testuser")]
    assert not strays, f"test fixtures in the production corpus: {strays}"

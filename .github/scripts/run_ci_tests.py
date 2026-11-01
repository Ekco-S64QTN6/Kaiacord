"""Run focused, offline CI tests for the changed code.

The full suite is a local/manual activity: PR checks should not boot Ollama,
GPU models, external APIs, or every unrelated subsystem. Select changed tests,
add the repository's cheap static invariants, and compile production Python.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tools" / "tests"
BASELINE = (
    TESTS / "unit" / "test_suite_hygiene.py",
    TESTS / "unit" / "test_chat_model_calls.py",
    TESTS / "unit" / "test_no_shadowed_imports.py",
)

# Modules whose tests are intentionally named by behavior rather than filename.
RELATED_TESTS = {
    **{f"finetune/{name}": ("tools/tests/unit/test_finetune_dataset.py",)
       for name in ("kaia_quality.py", "01_convert_logs.py", "01f_check_dataset.py",
                    "05c_evaluate_persona.py")},
    "utils/core/response_filter.py": (
        "tools/tests/unit/test_response_filters.py",
        "tools/tests/unit/test_ellipsis_salvage.py",
    ),
    "utils/core/kaia_rag_persistence.py": ("tools/tests/unit/test_telemetry_honesty.py",),
    "utils/infrastructure/system/shutdown_fixed.py": ("tools/tests/unit/test_telemetry_honesty.py",),
    "utils/core/context_enricher.py": (
        "tools/tests/unit/test_context_enricher_files.py",
        "tools/tests/unit/test_context_enricher_links.py",
        "tools/tests/unit/test_enrich_process_lifecycle.py",
    ),
    "utils/core/sanitizer.py": (
        "tools/tests/unit/test_context_enricher_files.py",
        "tools/tests/unit/test_sanitize_cap.py",
        "tools/tests/unit/test_channel_memory_scaffolding.py",
        "tools/tests/unit/test_reactions_and_logging.py",
    ),
    "utils/news/kaia_news.py": (
        "tools/tests/unit/test_news_manager.py",
        "tools/tests/unit/test_news_retrieval.py",
        "tools/tests/unit/test_news_and_short_queries.py",
    ),
    "utils/social/kaia_twitter.py": (
        "tools/tests/unit/test_kaia_twitter.py",
        "tools/tests/unit/test_x_auth_recovery.py",
    ),
    "utils/audio/strudel_source.py": (
        "tools/tests/unit/test_strudel_source_restart.py",
        "tools/tests/unit/test_strudel_music.py",
        "tools/tests/unit/test_strudel_session_lifecycle.py",
    ),
    "utils/audio/records.py": ("tools/tests/unit/test_records_startup_cleanup.py",
                               "tools/tests/unit/test_dj_dashboard.py"),
    "utils/audio/dj_dashboard.py": ("tools/tests/unit/test_records.py",),
    "utils/commands/music_handler.py": ("tools/tests/unit/test_records_startup_cleanup.py",),
    "utils/social/agent_board_verify.py": ("tools/tests/unit/test_agent_boards.py",),
    "utils/core/context_enricher.py": ("tools/tests/unit/test_context_enricher_links.py",),
    "utils/core/kaia_dream.py": ("tools/tests/unit/test_memory_anchors.py",),
    "utils/core/relationship_manager.py": (
        "tools/tests/unit/test_memory_anchors.py",
        "tools/tests/unit/test_relationship_events.py",
    ),
    "utils/core/sanitizer.py": ("tools/tests/unit/test_reactions_and_logging.py",),
    "utils/core/safety_pipeline.py": ("tools/tests/unit/test_response_filters.py",),
    "utils/admin/sources.py": ("tools/tests/unit/test_admin_dashboard.py",),
    "utils/audio/process_lifecycle.py": (
        "tools/tests/unit/test_records.py",
        "tools/tests/unit/test_strudel_source_restart.py",
        "tools/tests/unit/test_radio_close_stream.py",
    ),
    "utils/audio/strudel_engine.py": ("tools/tests/unit/test_strudel_source_restart.py",),
    "utils/commands/art_handler.py": (
        "tools/tests/unit/test_kaia_sheep.py",
        "tools/tests/unit/test_art_intent.py",
    ),
    "utils/radio/kiwi.py": (
        "tools/tests/unit/test_radio_close_stream.py",
        "tools/tests/unit/test_radio_listening.py",
        "tools/tests/unit/test_radio_live_cleanup.py",
    ),
    "utils/radio/scanner.py": ("tools/tests/unit/test_local_scanner.py", "tools/tests/unit/test_ledger_repair.py"),
    "utils/radio/waterfall.py": ("tools/tests/unit/test_local_scanner.py",),
    "utils/radio/ledger.py": (
        "tools/tests/unit/test_local_scanner.py",
        "tools/tests/unit/test_ledger_repair.py",
        "tools/tests/unit/test_radio_ledger_concurrency.py",
    ),
}


def changed_paths() -> list[str]:
    base = os.environ.get("CI_DIFF_BASE", "").strip()
    head = os.environ.get("CI_DIFF_HEAD", "HEAD").strip() or "HEAD"
    if not base or set(base) == {"0"}:
        # New branch/manual run: inspect the current commit only.
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", head],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
    else:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRT", base, head],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def select_tests(paths: list[str]) -> list[Path]:
    selected = {p for p in BASELINE if p.is_file()}
    available = {
        p.relative_to(ROOT).as_posix(): p
        for sub in ("unit", "integration")
        for p in (TESTS / sub).rglob("test_*.py")
    }

    for rel in paths:
        if rel in available:
            selected.add(available[rel])
            continue
        if not rel.endswith(".py") or rel.startswith("tools/tests/"):
            continue

        # TTRPG has its own path-triggered workflow, but run the focused suite
        # here too when the underlying game logic itself changes.
        if rel.startswith("utils/ttrpg/"):
            selected.update(p for name, p in available.items()
                            if name.startswith("tools/tests/unit/ttrpg/"))
            continue

        for test_rel in RELATED_TESTS.get(rel, ()):
            if test_rel in available:
                selected.add(available[test_rel])

        stem = Path(rel).stem
        direct = [p for name, p in available.items() if Path(name).name == f"test_{stem}.py"]
        selected.update(direct)

    return sorted(selected)


def main() -> int:
    paths = changed_paths()
    tests = select_tests(paths)

    print("Changed paths:")
    print("\n".join(f"  {p}" for p in paths) or "  (none detected)")
    print("Focused test files:")
    for test in tests:
        print(f"  {test.relative_to(ROOT).as_posix()}")

    # Syntax checks are cheap and do not import modules, connect to services,
    # or start model runners.
    for root_name in ("utils", "tools"):
        result = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", root_name],
            cwd=ROOT,
        )
        if result.returncode:
            return result.returncode

    # These checks are deterministic unit tests only. Never include tests
    # needing an external service, network, GPU, or a long-running sweep.
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q",
            "-m", "not ollama and not gpu and not slow and not network",
            *[str(p.relative_to(ROOT)) for p in tests],
        ],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())

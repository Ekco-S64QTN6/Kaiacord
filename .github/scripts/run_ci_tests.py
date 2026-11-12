"""Run focused, offline CI tests for the changed code.

The full suite is a local/manual activity: PR checks should not boot Ollama,
GPU models, external APIs, or every unrelated subsystem. Select changed tests,
add the repository's cheap static invariants, and compile production Python.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tools" / "tests"
BASELINE = (
    TESTS / "unit" / "test_suite_hygiene.py",
    TESTS / "unit" / "test_chat_model_calls.py",
    TESTS / "unit" / "test_no_shadowed_imports.py",
    TESTS / "unit" / "test_no_undefined_globals.py",
)

# Modules whose tests are intentionally named by behavior rather than filename.
RELATED_TESTS = {
    **{f"finetune/{name}": ("tools/tests/unit/test_finetune_dataset.py",)
       for name in ("kaia_quality.py", "01_convert_logs.py", "01f_check_dataset.py",
                    "05c_evaluate_persona.py")},
    ".github/scripts/run_ci_tests.py": ("tools/tests/unit/test_ci_test_selection.py",),
    "utils/core/response_filter.py": (
        "tools/tests/unit/test_response_filters.py",
        "tools/tests/unit/test_ellipsis_salvage.py",
    ),
    "utils/core/kaia_rag_indexer.py": ("tools/tests/unit/test_rag_index_hygiene.py",),
    "utils/core/kaia_proactive.py": ("tools/tests/unit/test_proactive_dedup.py",),
    "utils/infrastructure/system/kaia_sysmon.py": (
        "tools/tests/unit/test_sysmon_subprocess_lifecycle.py",
    ),
    "utils/ttrpg/rpg_social_handler.py": (
        "tools/tests/unit/ttrpg/test_world_event_async_io.py",
    ),
    "utils/ttrpg/broadcast.py": (
        "tools/tests/unit/ttrpg/test_world_event_async_io.py",
    ),
    "utils/infrastructure/system/bot_state.py": (
        "tools/tests/unit/test_bot_state_save.py",
        "tools/tests/unit/test_channel_memory_scaffolding.py",
        "tools/tests/unit/test_dm_privacy.py",
        "tools/tests/unit/test_monologue_observation.py",
    ),
    "utils/core/kaia_art_intent.py": ("tools/tests/unit/test_art_intent.py",),
    "utils/infrastructure/monitoring/async_lock_metrics.py": ("tools/tests/unit/test_async_lock_metrics.py",),
    "utils/ttrpg/session_manager.py": (
        "tools/tests/unit/test_async_lock_metrics.py",
        "tools/tests/unit/ttrpg/test_rpg_serialization.py",
    ),
    "utils/ttrpg/character_manager.py": ("tools/tests/unit/test_async_lock_metrics.py",),
    "utils/commands/sysmon_handler.py": ("tools/tests/unit/test_async_lock_metrics.py",),
    "utils/core/background_tasks.py": (
        "tools/tests/unit/test_rag_refresh_callers.py",
        "tools/tests/unit/test_news_manager.py",
        "tools/tests/unit/test_monologue_observation.py",
        "tools/tests/unit/test_news_followup_retry.py",
        "tools/tests/unit/test_background_task_processes.py",
        "tools/tests/unit/ttrpg/test_world_event_async_io.py",
    ),
    "utils/commands/news_handler.py": ("tools/tests/unit/test_command_boxes.py",),
    "tools/maintenance/scrape_tech_news.py": ("tools/tests/unit/test_news_manager.py",),
    "tools/maintenance/update_kaia_news.py": ("tools/tests/unit/test_news_brief.py",),
    "utils/commands/reindex_handler.py": ("tools/tests/unit/test_rag_refresh_callers.py",),
    "tools/maintenance/reindex_rag.py": ("tools/tests/unit/test_rag_refresh_callers.py",),
    "Kaiacord.py": ("tools/tests/unit/test_rag_refresh_callers.py",),
    "utils/core/kaia_rag_query.py": (
        "tools/tests/unit/test_rag_index_hygiene.py",
        "tools/tests/unit/test_rag_identity_scoping.py",
    ),
    "utils/core/kaia_rag_persistence.py": ("tools/tests/unit/test_telemetry_honesty.py",),
    "utils/infrastructure/system/shutdown_fixed.py": (
        "tools/tests/unit/test_telemetry_honesty.py",
        "tools/tests/unit/test_async_task_registry.py",
        "tools/tests/unit/test_shutdown_prelude.py",
        "tools/tests/unit/test_bot_state_save.py",
    ),
    "utils/infrastructure/monitoring/async_task_registry.py": ("tools/tests/unit/test_async_task_registry.py",),
    "utils/core/context_enricher.py": (
        "tools/tests/unit/test_context_enricher_files.py",
        "tools/tests/unit/test_context_enricher_links.py",
        "tools/tests/unit/test_enrich_process_lifecycle.py",
    ),
    "utils/core/message_processor.py": (
        "tools/tests/unit/test_channel_memory_scaffolding.py",
        "tools/tests/unit/test_reactions_and_logging.py",
        "tools/tests/unit/test_code_blocks.py",
        "tools/tests/unit/test_speaker_heuristics.py",
        "tools/tests/unit/test_dm_privacy.py",
        "tools/tests/unit/test_vision_fetch_security.py",
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
    "utils/core/kaia_dream.py": ("tools/tests/unit/test_memory_anchors.py", "tools/tests/unit/test_beliefs_store.py",
                                 "tools/tests/unit/test_memory_layer_regressions.py"),
    "utils/core/relationship_manager.py": (
        "tools/tests/unit/test_memory_anchors.py",
        "tools/tests/unit/test_relationship_events.py",
    ),
    "utils/core/safety_pipeline.py": ("tools/tests/unit/test_response_filters.py",),
    "utils/admin/sources.py": ("tools/tests/unit/test_admin_dashboard.py",),
    "utils/audio/process_lifecycle.py": (
        "tools/tests/unit/test_records.py",
        "tools/tests/unit/test_strudel_source_restart.py",
        "tools/tests/unit/test_radio_close_stream.py",
    ),
    "utils/audio/strudel_engine.py": (
        "tools/tests/unit/test_strudel_source_restart.py",
        "tools/tests/unit/test_strudel_engine_environment.py",
        "tools/tests/unit/test_strudel_session_lifecycle.py",
    ),
    "utils/audio/strudel_session.py": ("tools/tests/unit/test_strudel_session_lifecycle.py",),
    "utils/audio/strudel_session.py": ("tools/tests/unit/test_strudel_session_lifecycle.py",),
    "utils/commands/art_handler.py": (
        "tools/tests/unit/test_kaia_sheep.py",
        "tools/tests/unit/test_art_intent.py",
    ),
    "utils/radio/kiwi.py": (
        "tools/tests/unit/test_radio_close_stream.py",
        "tools/tests/unit/test_radio_listening.py",
        "tools/tests/unit/test_radio_live_cleanup.py",
    ),
    "utils/radio/scanner.py": ("tools/tests/unit/test_local_scanner.py", "tools/tests/unit/test_ledger_repair.py",
                               "tools/tests/unit/test_scanner_streets.py"),
    "utils/radio/streets.py": ("tools/tests/unit/test_scanner_streets.py",),
    "tools/maintenance/fetch_street_names.py": ("tools/tests/unit/test_scanner_streets.py",),
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

        # Apply explicit behavior mappings before the TTRPG broad-suite
        # shortcut; otherwise the early continue below silently drops them.
        for test_rel in RELATED_TESTS.get(rel, ()):
            if test_rel in available:
                selected.add(available[test_rel])

        # TTRPG has its own path-triggered workflow, but run the focused suite
        # here too when the underlying game logic itself changes.
        if rel.startswith("utils/ttrpg/"):
            selected.update(p for name, p in available.items()
                            if name.startswith("tools/tests/unit/ttrpg/"))
            continue

        stem = Path(rel).stem
        direct = [p for name, p in available.items() if Path(name).name == f"test_{stem}.py"]
        selected.update(direct)
        selected.update(importing_tests(rel, available))

    return sorted(selected)


#: A module imported by more test files than this (yaml_config, the logger) is
#: left to its explicit mappings: running every importer would be the suite.
MAX_IMPORTERS = 40


def importing_tests(rel: str, available: dict) -> list[Path]:
    """Test files that import the changed module by name.

    Tests named for a behaviour rather than a file were reachable only through
    RELATED_TESTS, and a missing entry meant CI ran none of them: three
    kaia_rag_query tests failed on main for a week this way.
    """
    if not rel.endswith(".py"):
        return []
    dotted = rel[:-3].replace("/", ".")
    package, _, stem = dotted.rpartition(".")
    patterns = [re.compile(rf"\b{re.escape(dotted)}\b")]
    if package:
        patterns.append(re.compile(
            rf"from\s+{re.escape(package)}\s+import\s+(?:\([^)]*|[^\n]*)\b{re.escape(stem)}\b"))
    hits = []
    for path in available.values():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(p.search(text) for p in patterns):
            hits.append(path)
    return hits if len(hits) <= MAX_IMPORTERS else []


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

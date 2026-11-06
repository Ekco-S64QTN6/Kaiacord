"""Regression tests for the focused CI changed-module selector."""

import ast
from collections import Counter
from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[3]
SELECTOR = ROOT / ".github" / "scripts" / "run_ci_tests.py"


def _literal_related_test_map():
    tree = ast.parse(SELECTOR.read_text(encoding="utf-8"))
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RELATED_TESTS"
                for target in node.targets)
    )
    assert isinstance(assignment.value, ast.Dict)
    return assignment.value


def test_related_tests_has_no_duplicate_literal_module_keys():
    mapping = _literal_related_test_map()
    keys = [
        key.value for key in mapping.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    assert duplicates == []


def test_behavior_mappings_keep_every_context_enricher_and_sanitizer_suite():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    related = selector["RELATED_TESTS"]

    assert set(related["utils/core/context_enricher.py"]) == {
        "tools/tests/unit/test_context_enricher_files.py",
        "tools/tests/unit/test_context_enricher_links.py",
        "tools/tests/unit/test_enrich_process_lifecycle.py",
    }
    assert set(related["utils/core/sanitizer.py"]) == {
        "tools/tests/unit/test_context_enricher_files.py",
        "tools/tests/unit/test_sanitize_cap.py",
        "tools/tests/unit/test_channel_memory_scaffolding.py",
        "tools/tests/unit/test_reactions_and_logging.py",
    }


def test_changed_ci_selector_itself_selects_its_regression_test():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    selected = {
        path.relative_to(ROOT).as_posix()
        for path in selector["select_tests"]([".github/scripts/run_ci_tests.py"])
    }
    assert "tools/tests/unit/test_ci_test_selection.py" in selected



def test_art_intent_changes_select_the_art_intent_regression_suite():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    selected = {
        path.relative_to(ROOT).as_posix()
        for path in selector["select_tests"](["utils/core/kaia_art_intent.py"])
    }
    assert "tools/tests/unit/test_art_intent.py" in selected



def test_every_behavior_mapping_targets_an_existing_test_file():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    missing = sorted({
        test_path
        for test_paths in selector["RELATED_TESTS"].values()
        for test_path in test_paths
        if not (ROOT / test_path).is_file()
    })
    assert missing == []


def test_message_processor_changes_select_vision_fetch_security_regressions():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    selected = {
        path.relative_to(ROOT).as_posix()
        for path in selector["select_tests"](["utils/core/message_processor.py"])
    }
    assert "tools/tests/unit/test_vision_fetch_security.py" in selected



def test_rpg_lock_registry_changes_select_metrics_regressions():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    related_sources = (
        "utils/infrastructure/monitoring/async_lock_metrics.py",
        "utils/ttrpg/session_manager.py",
        "utils/ttrpg/character_manager.py",
        "utils/commands/sysmon_handler.py",
    )
    for source in related_sources:
        selected = {
            path.relative_to(ROOT).as_posix()
            for path in selector["select_tests"]([source])
        }
        assert "tools/tests/unit/test_async_lock_metrics.py" in selected



def test_bot_state_changes_select_snapshot_and_persistence_regressions():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    selected = {
        path.relative_to(ROOT).as_posix()
        for path in selector["select_tests"](["utils/infrastructure/system/bot_state.py"])
    }
    assert "tools/tests/unit/test_bot_state_save.py" in selected

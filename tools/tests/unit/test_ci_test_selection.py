"""Regression tests for the focused CI changed-module selector."""

import ast
from collections import Counter
from pathlib import Path
import runpy
import subprocess


ROOT = Path(__file__).resolve().parents[3]
SELECTOR = ROOT / ".github" / "scripts" / "run_ci_tests.py"

# This list is deliberately independent of RELATED_TESTS. These are
# behavior-only or high-fan-in contracts whose focused coverage must not
# disappear merely because someone deletes the production mapping.
REQUIRED_RELATED_TESTS = {
    ".github/scripts/run_ci_tests.py": (
        "tools/tests/unit/test_ci_test_selection.py",
    ),
    "utils/core/ingress.py": (
        "tools/tests/unit/test_ingress_now.py",
    ),
    "utils/core/kaia_rag_query.py": (
        "tools/tests/unit/test_rag_index_hygiene.py",
        "tools/tests/unit/test_rag_identity_scoping.py",
        "tools/tests/unit/test_rag_retrieval_metadata.py",
        "tools/tests/unit/test_rag_persistence_concurrency.py",
    ),
    "utils/core/kaia_rag_indexer.py": (
        "tools/tests/unit/test_rag_index_hygiene.py",
        "tools/tests/unit/test_rag_persistence_concurrency.py",
    ),
    "utils/core/message_processor.py": (
        "tools/tests/unit/test_dm_privacy.py",
        "tools/tests/unit/test_dm_trigger.py",
        "tools/tests/unit/test_command_gate_and_download_limits.py",
        "tools/tests/unit/test_vision_fetch_security.py",
        "tools/tests/unit/test_channel_memory_lifecycle.py",
    ),
    "utils/infrastructure/system/shutdown_fixed.py": (
        "tools/tests/unit/test_async_task_registry.py",
        "tools/tests/unit/test_shutdown_prelude.py",
    ),
    "utils/ttrpg/session_manager.py": (
        "tools/tests/unit/test_async_lock_metrics.py",
        "tools/tests/unit/ttrpg/test_rpg_serialization.py",
    ),
    "utils/audio/records.py": (
        "tools/tests/unit/test_records.py",
        "tools/tests/unit/test_dj_dashboard.py",
        "tools/tests/unit/test_records_session_listener_intent.py",
        "tools/tests/unit/test_dj_fx.py",
    ),
    "utils/audio/dj_dashboard.py": (
        "tools/tests/unit/test_dj_dashboard.py",
        "tools/tests/unit/test_records.py",
    ),
    "utils/audio/record_cues.py": (
        "tools/tests/unit/test_record_cues.py",
    ),
    "tools/maintenance/check_review_manifest.py": (
        "tools/tests/unit/test_review_manifest.py",
    ),
    "assets/dj/index.html": (
        "tools/tests/unit/test_dj_dashboard.py",
    ),
}


def _missing_required_related_tests(mapping):
    """Return independently required module/test mappings absent from mapping."""
    missing = []
    for module, required_tests in REQUIRED_RELATED_TESTS.items():
        actual_tests = mapping.get(module)
        if actual_tests is None:
            missing.append(f"{module}: missing required module mapping")
            continue
        missing.extend(
            f"{module} -> {test_path}"
            for test_path in required_tests
            if test_path not in actual_tests
        )
    return missing


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


def test_changed_ci_selector_itself_selects_its_regression_test():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    selected = {
        path.relative_to(ROOT).as_posix()
        for path in selector["select_tests"]([".github/scripts/run_ci_tests.py"])
    }
    assert "tools/tests/unit/test_ci_test_selection.py" in selected


def test_every_behavior_mapping_targets_an_existing_test_file():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    missing = sorted({
        test_path
        for test_paths in selector["RELATED_TESTS"].values()
        for test_path in test_paths
        if not (ROOT / test_path).is_file()
    })
    assert missing == []


def test_a_module_change_selects_tests_that_import_it_under_any_name():
    """kaia_rag_query's behaviour-named tests were never selected, and three of
    them failed on main unnoticed."""
    selector = runpy.run_path(str(SELECTOR))
    selected = {p.as_posix() for p in selector["select_tests"](["utils/core/kaia_rag_query.py"])}
    for name in ("test_news_and_short_queries.py", "test_tier1_features.py"):
        assert any(s.endswith("tools/tests/unit/" + name) for s in selected), name


def test_any_command_handler_change_selects_the_acceptance_matrix():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    for changed in ("utils/commands/sky_handler.py", "utils/commands/registry.py", "utils/commands/nightshift.py"):
        selected = {path.relative_to(ROOT).as_posix() for path in selector["select_tests"]([changed])}
        assert "tools/tests/unit/test_every_command_answers.py" in selected, changed


def test_every_related_mapping_is_selected():
    """A change to each module in RELATED_TESTS selects every test listed for it."""
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    missed = []
    for module, tests in selector["RELATED_TESTS"].items():
        selected = {p.relative_to(ROOT).as_posix() for p in selector["select_tests"]([module])}
        missed += [f"{module} -> {t}" for t in tests if t not in selected]
    assert not missed, missed


def test_required_behavior_mappings_remain_present_and_select_their_tests():
    """A deleted key or test path fails even if production and generic tests agree."""
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    mapping = selector["RELATED_TESTS"]
    assert _missing_required_related_tests(mapping) == []

    available = {
        p.relative_to(ROOT).as_posix()
        for sub in ("unit", "integration")
        for p in (ROOT / "tools" / "tests" / sub).rglob("test_*.py")
    }
    for module, required_tests in REQUIRED_RELATED_TESTS.items():
        selected = {
            path.relative_to(ROOT).as_posix()
            for path in selector["select_tests"]([module])
        }
        for test_path in required_tests:
            assert test_path in available, test_path
            assert test_path in selected, f"{module} did not select {test_path}"


def test_required_mapping_guard_detects_a_deleted_production_entry():
    """Prove a missing required key is caught independently of RELATED_TESTS."""
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    mapping = dict(selector["RELATED_TESTS"])
    removed_module = "utils/audio/records.py"
    del mapping[removed_module]

    assert _missing_required_related_tests(mapping) == [
        f"{removed_module}: missing required module mapping"
    ]


def test_required_mapping_guard_detects_a_deleted_behavior_test():
    """A surviving module key cannot silently lose one of its required tests."""
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    mapping = dict(selector["RELATED_TESTS"])
    module = "utils/audio/records.py"
    mapping[module] = tuple(
        path for path in mapping[module]
        if path != "tools/tests/unit/test_records.py"
    )

    assert _missing_required_related_tests(mapping) == [
        f"{module} -> tools/tests/unit/test_records.py"
    ]


def test_every_high_fan_in_module_has_independent_related_test_mapping():
    """The import cap must not turn a high-fan-in production change into zero tests."""
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    available = {
        p.relative_to(ROOT).as_posix(): p
        for sub in ("unit", "integration")
        for p in (ROOT / "tools" / "tests" / sub).rglob("test_*.py")
    }
    # Read the test corpus once. The selector's import matching remains the
    # single source of truth; the cache only avoids repeated filesystem reads.
    test_sources = {
        path: path.read_text(encoding="utf-8")
        for path in available.values()
    }
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    production_paths = sorted(
        raw.decode("utf-8")
        for raw in tracked.split(b"\0")
        if raw and not raw.decode("utf-8").startswith("tools/tests/")
    )

    mapping = selector["RELATED_TESTS"]
    cap = selector["MAX_IMPORTERS"]
    uncovered = []
    for module in production_paths:
        importers = selector["find_importers"](module, available, test_sources)
        if len(importers) <= cap:
            continue
        mapped = mapping.get(module, ())
        required = REQUIRED_RELATED_TESTS.get(module)
        if not mapped or not required:
            uncovered.append(
                f"{module}: {len(importers)} importers, "
                "but no independent required behavior mapping"
            )
            continue
        missing = sorted(set(required) - set(mapped))
        if missing:
            uncovered.append(
                f"{module}: required tests absent from RELATED_TESTS: {missing}"
            )

    assert not uncovered, (
        "High-fan-in modules must keep explicit, independently guarded test "
        "mappings instead of being silently dropped at MAX_IMPORTERS:\n"
        + "\n".join(uncovered)
    )

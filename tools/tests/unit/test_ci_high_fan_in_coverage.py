"""Focused CI guard: every high-fan-in production module has independent tests."""

import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SELECTOR = ROOT / ".github" / "scripts" / "run_ci_tests.py"
RELATED_TEST_SELECTOR = ROOT / "tools" / "tests" / "unit" / "test_ci_test_selection.py"
REQUIRED_RELATED_TESTS = runpy.run_path(str(RELATED_TEST_SELECTOR))["REQUIRED_RELATED_TESTS"]


def _coverage_problems(select_tests, module, mapped, required, available) -> list:
    """Why a high-fan-in module's required tests would not run, if they would not.

    A required path that is only a string in the mapping is not coverage: the
    selector skips a mapped file that no longer exists, so a deleted or renamed
    behaviour test left the guard passing while the module ran without it.
    """
    problems = []
    missing = sorted(set(required) - set(mapped))
    if missing:
        problems.append(f"{module}: required tests absent from RELATED_TESTS: {missing}")
    gone = sorted(p for p in required if p not in available)
    if gone:
        problems.append(f"{module}: required tests that do not exist: {gone}")
    selected = {p.relative_to(ROOT).as_posix() for p in select_tests([module])}
    unselected = sorted(p for p in required if p in available and p not in selected)
    if unselected:
        problems.append(f"{module}: required tests the selector does not run for it: {unselected}")
    return problems


def test_a_required_test_that_is_gone_or_not_selected_is_reported():
    module = "utils/core/example.py"
    present = "tools/tests/unit/test_present.py"
    deleted = "tools/tests/unit/test_deleted.py"
    available = {present: ROOT / present}
    assert _coverage_problems(lambda paths: [ROOT / present], module, (present, deleted),
                              (present, deleted), available) == [
        f"{module}: required tests that do not exist: ['{deleted}']"]
    assert _coverage_problems(lambda paths: [], module, (present,), (present,), available) == [
        f"{module}: required tests the selector does not run for it: ['{present}']"]
    assert _coverage_problems(lambda paths: [ROOT / present], module, (present,), (present,),
                              available) == []


def test_every_related_tests_target_exists():
    selector = runpy.run_path(str(SELECTOR), run_name="ci_selector_test")
    gone = sorted(
        f"{module} -> {target}"
        for module, targets in selector["RELATED_TESTS"].items()
        for target in targets
        if not (ROOT / target).is_file()
    )
    assert not gone, "RELATED_TESTS names test files that do not exist:\n" + "\n".join(gone)


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
        uncovered += _coverage_problems(selector["select_tests"], module, mapped, required, available)

    assert not uncovered, (
        "High-fan-in modules must keep explicit, independently guarded test "
        "mappings instead of being silently dropped at MAX_IMPORTERS:\n"
        + "\n".join(uncovered)
    )

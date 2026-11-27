"""Focused CI guard: every high-fan-in production module has independent tests."""

import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SELECTOR = ROOT / ".github" / "scripts" / "run_ci_tests.py"
RELATED_TEST_SELECTOR = ROOT / "tools" / "tests" / "unit" / "test_ci_test_selection.py"
REQUIRED_RELATED_TESTS = runpy.run_path(str(RELATED_TEST_SELECTOR))["REQUIRED_RELATED_TESTS"]


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

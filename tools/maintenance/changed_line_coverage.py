#!/usr/bin/env python3
"""Report and gate coverage for added lines in changed production Python files.

Coverage is collected only from the focused offline tests selected by
.github/scripts/run_ci_tests.py. This is an incremental signal, not a claim of
whole-project or live-service coverage.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import PurePosixPath


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_python_lines(diff: str, prefix: str = "utils/") -> dict[str, set[int]]:
    """Return added line numbers from zero-context unified diff hunks."""
    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            candidate = line[6:]
            current = candidate if candidate.startswith(prefix) and candidate.endswith(".py") else None
        elif line.startswith("+++ /dev/null"):
            current = None
        elif line.startswith("@@ ") and current:
            match = _HUNK.match(line)
            if not match:
                continue
            start = int(match.group(1))
            count = int(match.group(2) or "1")
            if count:
                result.setdefault(current, set()).update(range(start, start + count))
    return result


def _normalise_coverage_path(raw: str) -> str | None:
    path = PurePosixPath(raw.replace("\\", "/"))
    parts = path.parts
    try:
        index = parts.index("utils")
    except ValueError:
        return None
    return PurePosixPath(*parts[index:]).as_posix()


def statement_lines(source: str) -> set[int]:
    """Lines a statement starts on, as coverage counts them; docstrings are not statements."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines = {node.lineno for node in ast.walk(tree) if isinstance(node, ast.stmt)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                lines.discard(first.lineno)
    return lines


def _unmeasured_statements(path: str) -> set[int] | None:
    """Statement lines of a file coverage never loaded, or None when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as stream:
            return statement_lines(stream.read())
    except OSError:
        return None


def changed_line_report(coverage: dict, changes: dict[str, set[int]], minimum: float,
                        statements_of=_unmeasured_statements) -> tuple[str, bool]:
    """Create a Markdown summary and return whether the changed-line floor passed.

    Only statements are measured. A comment, a blank line, a docstring or the
    continuation of a multi-line literal is in neither coverage list, and
    counting it as uncovered failed a comment-only change to a covered file.
    """
    files = coverage.get("files", {})
    normalised = {}
    for raw, data in files.items():
        key = _normalise_coverage_path(raw)
        if key:
            normalised[key] = data

    rows = []
    subsystems: dict[str, list[int]] = {}
    covered_total = 0
    measured_total = 0
    for path in sorted(changes):
        data = normalised.get(path)
        if data is None:
            # Never imported by the selected tests: every added statement is
            # uncovered. An unreadable file keeps the strictest reading.
            known = statements_of(path)
            data = {}
        else:
            known = set(data.get("executed_lines", [])) | set(data.get("missing_lines", []))
        executed = set(data.get("executed_lines", []))
        excluded = set(data.get("excluded_lines", []))
        measured = (changes[path] if known is None else changes[path] & known) - excluded
        covered = measured & executed
        count = len(measured)
        hits = len(covered)
        percent = (100.0 * hits / count) if count else 100.0
        rows.append((path, hits, count, percent, len(changes[path] & excluded)))
        parts = PurePosixPath(path).parts
        subsystem = parts[1] if len(parts) > 1 else "other"
        totals = subsystems.setdefault(subsystem, [0, 0])
        totals[0] += hits
        totals[1] += count
        covered_total += hits
        measured_total += count

    if measured_total:
        percent = 100.0 * covered_total / measured_total
        passed = percent >= minimum
        outcome = "PASS" if passed else "FAIL"
        lines = [
            "## Incremental changed-line coverage",
            "",
            f"**{outcome}: {covered_total}/{measured_total} added utils/*.py statements covered "
            f"({percent:.1f}%; required floor: {minimum:.1f}%).**",
            "",
            "| Subsystem | Covered / measured lines | Coverage |",
            "|---|---:|---:|",
        ]
        for subsystem, (hits, count) in sorted(subsystems.items()):
            lines.append(f"| {subsystem} | {hits}/{count} | {(100.0 * hits / count) if count else 100.0:.1f}% |")
        lines.extend([
            "",
            "| Changed file | Covered / measured lines | Coverage | Excluded |",
            "|---|---:|---:|---:|",
        ])
        lines.extend(
            f"| {path} | {hits}/{count} | {file_percent:.1f}% | {excluded} |"
            for path, hits, count, file_percent, excluded in rows
        )
    else:
        passed = True
        lines = [
            "## Incremental changed-line coverage",
            "",
            "No added production statements under utils/ were found in this change. "
            "The gate is informational for this PR.",
        ]

    lines.extend([
        "",
        "The coverage artifact is produced from the focused offline tests selected for this diff. "
        "It is not a whole-project, hardware, Ollama, or network coverage claim.",
        "",
    ])
    return "\n".join(lines), passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", default="coverage.json")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--minimum", type=float, default=20.0)
    parser.add_argument("--summary", default="coverage-summary.md")
    args = parser.parse_args()
    # A push's "before" is all zeros for a new ref, and empty outside CI.
    if not args.base.strip("0"):
        args.base = "origin/main"

    with open(args.coverage, encoding="utf-8") as stream:
        coverage = json.load(stream)
    diff = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--unified=0", "--diff-filter=ACMRT",
         f"{args.base}...{args.head}", "--", "utils"],
        check=True, capture_output=True, text=True,
    ).stdout
    changes = changed_python_lines(diff)
    summary, passed = changed_line_report(coverage, changes, args.minimum)
    with open(args.summary, "w", encoding="utf-8") as stream:
        stream.write(summary)
    print(summary)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

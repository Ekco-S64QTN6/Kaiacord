#!/usr/bin/env python3
"""Type-check the production files a change touches, against their own base.

A file may carry the mypy errors it already had; it may not gain any. Each
changed ``utils/*.py`` file is checked at the merge base and at the head with
the same flags, and the run fails when a file's error count went up. There is
no stored baseline to maintain: the base commit is the baseline.

Imports are not followed (``--follow-imports=skip``), so a file is judged on
its own text and an error elsewhere in the tree cannot fail an unrelated
change. That also means cross-module type errors are not seen here.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "utils/"
MYPY_FLAGS = [
    "--no-incremental",
    "--ignore-missing-imports",
    "--follow-imports=skip",
    "--show-error-codes",
    "--hide-error-context",
    "--no-color-output",
    "--no-error-summary",
]
_ERROR = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+)(?::\d+)?: error: (?P<text>.*)$")


def changed_files(name_status: str, prefix: str = PREFIX) -> dict[str, str | None]:
    """Map each changed production file at head to its path at base (None if new)."""
    result: dict[str, str | None] = {}
    for row in name_status.splitlines():
        parts = row.split("\t")
        status = parts[0][:1]
        if status == "R" and len(parts) == 3:
            old, new = parts[1], parts[2]
        elif status in ("M", "T") and len(parts) == 2:
            old, new = parts[1], parts[1]
        elif status in ("A", "C") and len(parts) >= 2:
            old, new = None, parts[-1]
        else:
            continue
        if new.startswith(prefix) and new.endswith(".py"):
            result[new] = old if old and old.endswith(".py") else None
    return result


def parse_errors(output: str) -> dict[str, list[tuple[int, str]]]:
    """Group mypy's error lines by file as (line, message)."""
    errors: dict[str, list[tuple[int, str]]] = {}
    for line in output.splitlines():
        match = _ERROR.match(line.strip())
        if match:
            errors.setdefault(match["path"], []).append((int(match["line"]), match["text"]))
    return errors


def compare(files: dict[str, str | None],
            base: dict[str, list[tuple[int, str]]],
            head: dict[str, list[tuple[int, str]]]) -> list[tuple[str, int, int, list[tuple[int, str]]]]:
    """Files whose error count rose: (path, before, after, errors not seen at base)."""
    regressions = []
    for path, old in sorted(files.items()):
        before = base.get(old, []) if old else []
        after = head.get(path, [])
        if len(after) <= len(before):
            continue
        seen = Counter(text for _, text in before)
        fresh = []
        for line, text in after:
            if seen[text]:
                seen[text] -= 1
            else:
                fresh.append((line, text))
        regressions.append((path, len(before), len(after), fresh))
    return regressions


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _mypy(paths: list[str], cwd: Path) -> dict[str, list[tuple[int, str]]]:
    if not paths:
        return {}
    done = subprocess.run([sys.executable, "-m", "mypy", *MYPY_FLAGS, *paths],
                          cwd=cwd, capture_output=True, text=True, check=False)
    # 0 is clean and 1 is "errors found"; anything else is mypy itself failing.
    if done.returncode not in (0, 1):
        raise RuntimeError(f"mypy failed ({done.returncode}):\n{done.stdout}\n{done.stderr}")
    return parse_errors(done.stdout)


def report(files, regressions, base, head) -> str:
    lines = ["## Type ratchet (mypy, changed utils/*.py files)", ""]
    if not files:
        lines.append("No production Python files under utils/ changed; nothing to check.")
        return "\n".join(lines) + "\n"
    lines += ["| Changed file | Errors at base | Errors at head |", "|---|---:|---:|"]
    for path, old in sorted(files.items()):
        before = len(base.get(old, [])) if old else 0
        lines.append(f"| {path} | {before if old else 'new'} | {len(head.get(path, []))} |")
    lines.append("")
    if regressions:
        lines.append("**FAIL: these files gained type errors.**")
        for path, before, after, fresh in regressions:
            lines += ["", f"`{path}`: {before} -> {after}"]
            lines += [f"- line {line}: {text}" for line, text in fresh]
    else:
        lines.append("**PASS: no changed file gained a type error.**")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("CI_DIFF_BASE", "") or "origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY", ""))
    args = parser.parse_args()
    if not args.base.strip("0"):
        args.base = "origin/main"

    merge_base = _git("merge-base", args.base, args.head).strip()
    files = changed_files(_git("diff", "--name-status", "-M", "--diff-filter=ACMRT",
                               merge_base, args.head, "--", PREFIX.rstrip("/")))
    head = _mypy(sorted(files), ROOT)
    base: dict[str, list[tuple[int, str]]] = {}
    olds = sorted({old for old in files.values() if old})
    if olds:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / "base"
            _git("worktree", "add", "--detach", str(tree), merge_base)
            try:
                base = _mypy(olds, tree)
            finally:
                _git("worktree", "remove", "--force", str(tree))
    regressions = compare(files, base, head)
    text = report(files, regressions, base, head)
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as stream:
            stream.write(text)
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())

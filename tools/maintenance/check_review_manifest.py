"""Validate the tracked-file review ledger against the Git index.

This checks inventory completeness and status evidence, not the quality of a
review. The ledger CSV excludes itself because a file cannot record its own
stable Git blob ID.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_REL = "docs/audits/repository-review-ledger.csv"
MANIFEST_PATH = ROOT / MANIFEST_REL
REQUIRED_COLUMNS = (
    "path",
    "blob_sha",
    "size_bytes",
    "category",
    "risk_tier",
    "review_status",
    "reviewed_blob_sha",
    "evidence",
    "follow_up",
)
ALLOWED_STATUSES = {"not_reviewed", "reviewed", "not_applicable"}
ALLOWED_RISKS = {"high", "medium", "low"}


def tracked_file_blobs(root: Path = ROOT) -> dict[str, str]:
    """Return tracked paths and their stage-zero blob IDs from the Git index."""
    result = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    tracked: dict[str, str] = {}
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, blob_sha, stage = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"cannot parse git ls-files entry: {entry!r}") from exc
        if stage != "0":
            raise RuntimeError(f"unmerged index entry for {path!r} (stage {stage})")
        if mode == "160000":
            # A gitlink is a submodule commit, not a file blob; this repository
            # inventory is explicitly for tracked file blobs.
            continue
        if path in tracked:
            raise RuntimeError(f"duplicate path from git index: {path}")
        tracked[path] = blob_sha
    return tracked


def read_rows(path: Path = MANIFEST_PATH) -> list[dict[str, str]]:
    """Read the CSV and require its documented schema."""
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"empty ledger: {path}")
        missing = sorted(set(REQUIRED_COLUMNS) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"ledger is missing columns: {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"extra CSV columns at {path}:{line_number}")
            rows.append({column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS})
    return rows


def validate_inventory(
    tracked: Mapping[str, str],
    rows: Sequence[Mapping[str, str]],
    *,
    manifest_rel: str = MANIFEST_REL,
) -> list[str]:
    """Return all completeness, blob-identity and status-contract violations."""
    errors: list[str] = []
    expected = set(tracked) - {manifest_rel}
    seen: dict[str, int] = {}

    for index, row in enumerate(rows, start=2):
        path = row.get("path", "")
        if not path:
            errors.append(f"row {index}: empty path")
            continue
        if path == manifest_rel:
            errors.append(f"row {index}: the ledger must not contain itself")
            continue
        if path in seen:
            errors.append(f"row {index}: duplicate path {path!r} (first at row {seen[path]})")
            continue
        seen[path] = index

        current_sha = tracked.get(path)
        if current_sha is None:
            errors.append(f"row {index}: path is not tracked: {path}")
        elif row.get("blob_sha") != current_sha:
            errors.append(
                f"row {index}: stale blob SHA for {path} "
                f"(ledger {row.get('blob_sha')}, index {current_sha})"
            )

        status = row.get("review_status", "")
        if status not in ALLOWED_STATUSES:
            errors.append(f"row {index}: invalid review_status {status!r} for {path}")
        risk = row.get("risk_tier", "")
        if risk not in ALLOWED_RISKS:
            errors.append(f"row {index}: invalid risk_tier {risk!r} for {path}")
        if not row.get("category"):
            errors.append(f"row {index}: empty category for {path}")

        reviewed_sha = row.get("reviewed_blob_sha", "")
        evidence = row.get("evidence", "")
        if status == "reviewed":
            if current_sha is None or reviewed_sha != current_sha:
                errors.append(f"row {index}: reviewed_blob_sha must match current blob for {path}")
            if not evidence:
                errors.append(f"row {index}: reviewed row requires evidence for {path}")
        elif status == "not_applicable" and not evidence:
            errors.append(f"row {index}: not_applicable row requires an explanation for {path}")
        elif status == "not_reviewed" and reviewed_sha:
            errors.append(f"row {index}: not_reviewed row must not carry reviewed_blob_sha for {path}")

        try:
            size = int(row.get("size_bytes", ""))
            if size < 0:
                raise ValueError
        except ValueError:
            errors.append(f"row {index}: invalid size_bytes for {path}")

    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    errors.extend(f"missing tracked file: {path}" for path in missing)
    errors.extend(f"stale manifest path: {path}" for path in extra)
    return errors


def main() -> int:
    try:
        tracked = tracked_file_blobs()
        rows = read_rows()
        errors = validate_inventory(tracked, rows)
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        print(f"review ledger: cannot validate: {exc}", file=sys.stderr)
        return 2

    if errors:
        print(f"review ledger: {len(errors)} error(s)")
        for error in errors:
            print(f" - {error}")
        return 1

    reviewed = sum(row["review_status"] == "reviewed" for row in rows)
    not_applicable = sum(row["review_status"] == "not_applicable" for row in rows)
    pending = sum(row["review_status"] == "not_reviewed" for row in rows)
    print(
        f"review ledger complete: {len(rows)} files; "
        f"{reviewed} reviewed, {not_applicable} not applicable, {pending} not reviewed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

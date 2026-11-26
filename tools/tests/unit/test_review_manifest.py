"""The review ledger must remain complete and must not inherit stale review marks."""
import csv
import subprocess

import pytest

from tools.maintenance import check_review_manifest as checker
from tools.maintenance.check_review_manifest import (
    REQUIRED_COLUMNS,
    read_rows,
    tracked_file_blobs,
    validate_inventory,
)


def _row(path="utils/core/processor.py", sha="abc123", **changes):
    row = {
        "path": path,
        "blob_sha": sha,
        "size_bytes": "10",
        "category": "python_source",
        "risk_tier": "high",
        "review_status": "not_reviewed",
        "reviewed_blob_sha": "",
        "evidence": "",
        "follow_up": "",
    }
    row.update(changes)
    assert set(row) == set(REQUIRED_COLUMNS)
    return row


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_tracked_file_blobs_reads_stage_zero_files_and_paths_with_spaces(tmp_path):
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    file = tmp_path / "file with spaces.py"
    file.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "file with spaces.py"], cwd=tmp_path, check=True)
    expected = subprocess.run(
        ["git", "hash-object", "file with spaces.py"],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    ).stdout.strip()

    assert tracked_file_blobs(tmp_path) == {"file with spaces.py": expected}


def test_read_rows_round_trips_the_documented_csv_schema(tmp_path):
    path = tmp_path / "ledger.csv"
    expected = [_row()]
    _write_csv(path, expected)
    assert read_rows(path) == expected


def test_read_rows_rejects_missing_columns_and_extra_csv_fields(tmp_path):
    missing = tmp_path / "missing.csv"
    missing.write_text("path,blob_sha\na.py,abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        read_rows(missing)

    extra = tmp_path / "extra.csv"
    extra.write_text(
        ",".join(REQUIRED_COLUMNS) + "\n"
        + "a.py,abc,1,python_source,high,not_reviewed,,,," + "extra\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="extra CSV columns"):
        read_rows(extra)


def test_complete_inventory_accepts_pending_files_and_excludes_only_itself():
    tracked = {
        "utils/core/processor.py": "abc123",
        "docs/guide.md": "def456",
        "docs/audits/repository-review-ledger.csv": "self-sha",
    }
    rows = [
        _row(),
        _row(
            path="docs/guide.md",
            sha="def456",
            category="documentation",
            risk_tier="low",
        ),
    ]
    assert validate_inventory(tracked, rows) == []


def test_complete_inventory_accepts_a_blob_scoped_review_with_evidence():
    tracked = {"utils/core/processor.py": "abc123"}
    row = _row(
        review_status="reviewed",
        reviewed_blob_sha="abc123",
        evidence="Reviewed parser bounds and malformed-input regression tests.",
    )
    assert validate_inventory(tracked, [row]) == []


def test_not_applicable_rows_need_an_explanation():
    tracked = {"assets/example.webp": "abc123"}
    row = _row(
        path="assets/example.webp",
        category="asset",
        risk_tier="low",
        review_status="not_applicable",
    )
    assert any(
        "not_applicable row requires an explanation" in error
        for error in validate_inventory(tracked, [row])
    )


def test_inventory_reports_every_missing_tracked_file():
    tracked = {
        "utils/core/processor.py": "abc123",
        "utils/audio/records.py": "def456",
    }
    errors = validate_inventory(tracked, [_row()])
    assert errors == ["missing tracked file: utils/audio/records.py"]


def test_inventory_rejects_untracked_paths_and_duplicate_rows():
    tracked = {"utils/core/processor.py": "abc123"}
    rows = [
        _row(),
        _row(path="deleted/old_file.py", sha="gone"),
        _row(),
    ]
    errors = validate_inventory(tracked, rows)
    assert "stale manifest path: deleted/old_file.py" in errors
    assert any("duplicate path" in error for error in errors)


def test_inventory_rejects_a_blob_change_instead_of_inheriting_review_state():
    tracked = {"utils/core/processor.py": "new-sha"}
    rows = [
        _row(
            sha="old-sha",
            review_status="reviewed",
            reviewed_blob_sha="old-sha",
            evidence="Reviewed the old implementation and its tests.",
        )
    ]
    errors = validate_inventory(tracked, rows)
    assert any("stale blob SHA" in error for error in errors)
    assert any("reviewed_blob_sha must match current blob" in error for error in errors)


def test_reviewed_rows_require_matching_blob_identity_and_evidence():
    tracked = {"utils/core/processor.py": "abc123"}
    rows = [_row(review_status="reviewed")]
    errors = validate_inventory(tracked, rows)
    assert "row 2: reviewed_blob_sha must match current blob for utils/core/processor.py" in errors
    assert "row 2: reviewed row requires evidence for utils/core/processor.py" in errors


def test_not_reviewed_rows_cannot_carry_old_review_evidence():
    tracked = {"utils/core/processor.py": "abc123"}
    row = _row(reviewed_blob_sha="abc123")
    assert any(
        "not_reviewed row must not carry reviewed_blob_sha" in error
        for error in validate_inventory(tracked, [row])
    )


def test_inventory_rejects_invalid_status_risk_category_and_size():
    tracked = {"utils/core/processor.py": "abc123"}
    row = _row(review_status="done", risk_tier="critical", category="", size_bytes="-1")
    errors = validate_inventory(tracked, [row])
    assert any("invalid review_status" in error for error in errors)
    assert any("invalid risk_tier" in error for error in errors)
    assert any("empty category" in error for error in errors)
    assert any("invalid size_bytes" in error for error in errors)


def test_inventory_rejects_empty_paths_and_self_references():
    tracked = {"utils/core/processor.py": "abc123"}
    errors = validate_inventory(
        tracked,
        [_row(path=""), _row(path="docs/audits/repository-review-ledger.csv")],
    )
    assert "row 2: empty path" in errors
    assert "row 3: the ledger must not contain itself" in errors


def test_inventory_rejects_duplicate_path_records():
    tracked = {"utils/core/processor.py": "abc123"}
    errors = validate_inventory(tracked, [_row(), _row()])
    assert any("duplicate path" in error for error in errors)


def test_read_rows_rejects_an_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty ledger"):
        read_rows(path)


def test_cli_main_reports_the_current_pending_review_counts(monkeypatch, capsys):
    monkeypatch.setattr(
        checker, "tracked_file_blobs",
        lambda: {"utils/core/processor.py": "abc123"},
    )
    monkeypatch.setattr(checker, "read_rows", lambda: [_row()])
    assert checker.main() == 0
    assert "1 files; 0 reviewed, 0 not applicable, 1 not reviewed" in capsys.readouterr().out


def test_cli_main_returns_one_when_the_ledger_is_incomplete(monkeypatch, capsys):
    monkeypatch.setattr(
        checker, "tracked_file_blobs",
        lambda: {"utils/core/processor.py": "abc123"},
    )
    monkeypatch.setattr(checker, "read_rows", lambda: [])
    assert checker.main() == 1
    assert "missing tracked file" in capsys.readouterr().out


def test_cli_main_returns_two_when_the_git_inventory_cannot_be_read(monkeypatch, capsys):
    def fail_inventory():
        raise RuntimeError("no git index")

    monkeypatch.setattr(checker, "tracked_file_blobs", fail_inventory)
    assert checker.main() == 2
    assert "cannot validate: no git index" in capsys.readouterr().err

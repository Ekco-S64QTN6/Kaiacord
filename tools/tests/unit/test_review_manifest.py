"""The review ledger must remain complete and must not inherit stale review marks."""
from tools.maintenance.check_review_manifest import (
    REQUIRED_COLUMNS,
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
    ]
    errors = validate_inventory(tracked, rows)
    assert any("duplicate path" not in error for error in errors)
    assert "stale manifest path: deleted/old_file.py" in errors


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


def test_not_applicable_rows_need_a_reason():
    tracked = {"assets/example.webp": "abc123"}
    row = _row(
        path="assets/example.webp",
        category="binary_asset",
        risk_tier="low",
        review_status="not_applicable",
    )
    assert any(
        "not_applicable row requires an explanation" in error
        for error in validate_inventory(tracked, [row])
    )


def test_not_reviewed_rows_cannot_carry_old_review_evidence():
    tracked = {"utils/core/processor.py": "abc123"}
    row = _row(reviewed_blob_sha="abc123")
    assert any(
        "not_reviewed row must not carry reviewed_blob_sha" in error
        for error in validate_inventory(tracked, [row])
    )


def test_inventory_rejects_duplicate_path_records():
    tracked = {"utils/core/processor.py": "abc123"}
    errors = validate_inventory(tracked, [_row(), _row()])
    assert any("duplicate path" in error for error in errors)

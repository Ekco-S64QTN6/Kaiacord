"""Bulk RPG file scans report damaged records without hiding valid neighbors."""
import asyncio
import json

from utils.ttrpg import (
    character_manager,
    housing,
    housing_transactions,
    record_scan,
    world_state,
)


def test_character_scan_reports_bad_files_and_keeps_valid_and_legacy_records(
    tmp_path, monkeypatch
):
    directory = tmp_path / "characters"
    directory.mkdir()
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(directory))

    (directory / "good.json").write_text(json.dumps({
        "user_id": "good", "character_name": "Good", "inventory": [],
    }), encoding="utf-8")
    legacy_path = directory / "legacy.json"
    legacy_path.write_text(json.dumps({
        "character_name": "Legacy", "inventory": [],
    }), encoding="utf-8")
    corrupt_path = directory / "corrupt.json"
    corrupt_bytes = b"{broken character json"
    corrupt_path.write_bytes(corrupt_bytes)
    root_path = directory / "array.json"
    root_bytes = b"[]"
    root_path.write_bytes(root_bytes)
    mismatch_path = directory / "mismatch.json"
    mismatch_path.write_text(json.dumps({
        "user_id": "someone-else", "character_name": "Wrong owner",
    }), encoding="utf-8")

    report = character_manager._load_all_sync_report()

    assert {sheet["user_id"] for sheet in report.records} == {"good", "legacy"}
    assert next(
        sheet for sheet in report.records if sheet["user_id"] == "legacy"
    )["character_name"] == "Legacy"
    assert {failure.owner_id for failure in report.failures} == {
        "corrupt", "array", "mismatch",
    }
    assert not report.complete
    assert corrupt_path.read_bytes() == corrupt_bytes
    assert root_path.read_bytes() == root_bytes
    assert "user_id" not in json.loads(legacy_path.read_text(encoding="utf-8"))


def test_single_character_load_rejects_a_sheet_owned_by_another_user(
    tmp_path, monkeypatch
):
    directory = tmp_path / "characters"
    directory.mkdir()
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(directory))
    path = directory / "alice.json"
    record = {
        "user_id": "bob",
        "character_name": "Bob",
        "inventory": ["void_band"],
    }
    path.write_text(json.dumps(record), encoding="utf-8")

    import pytest
    with pytest.raises(ValueError, match="does not match requested owner"):
        character_manager._load_sync("alice")

    # The wrong-owner payload is neither returned nor rewritten.
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_single_character_load_migrates_legacy_owner_from_filename(
    tmp_path, monkeypatch
):
    directory = tmp_path / "characters"
    directory.mkdir()
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(directory))
    (directory / "legacy.json").write_text(json.dumps({
        "character_name": "Legacy",
        "inventory": [],
    }), encoding="utf-8")

    sheet = character_manager._load_sync("legacy")

    assert sheet["user_id"] == "legacy"
    assert sheet["character_name"] == "Legacy"


def test_character_list_compatibility_wrapper_returns_valid_records_and_logs_failures(
    tmp_path, monkeypatch
):
    directory = tmp_path / "characters"
    directory.mkdir()
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(directory))
    (directory / "ok.json").write_text(
        json.dumps({"user_id": "ok", "character_name": "Readable", "inventory": []}),
        encoding="utf-8",
    )
    (directory / "bad.json").write_text("{", encoding="utf-8")
    reported = []
    monkeypatch.setattr(
        character_manager,
        "log_scan_failures",
        lambda name, report: reported.append((name, report)),
    )

    records = character_manager._load_all_sync()

    assert [record["user_id"] for record in records] == ["ok"]
    assert len(reported) == 1
    assert reported[0][0] == "character sheets"
    assert reported[0][1].failures[0].owner_id == "bad"


def test_character_async_report_recovers_journals_and_exposes_partial_scan(
    tmp_path, monkeypatch
):
    directory = tmp_path / "characters"
    directory.mkdir()
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(directory))
    (directory / "ok.json").write_text(
        json.dumps({"user_id": "ok", "character_name": "Readable", "inventory": []}),
        encoding="utf-8",
    )
    (directory / "bad.json").write_text("not json", encoding="utf-8")
    events = []

    async def recover_world():
        events.append("world")

    async def recover_housing():
        events.append("housing")

    monkeypatch.setattr(
        world_state, "recover_pending_world_state_transaction", recover_world
    )
    monkeypatch.setattr(
        housing_transactions, "recover_all_pending_housing_transactions",
        recover_housing,
    )
    monkeypatch.setattr(character_manager, "log_scan_failures", lambda *_: None)

    report = asyncio.run(character_manager.load_all_report())

    assert events == ["world", "housing"]
    assert [record["user_id"] for record in report.records] == ["ok"]
    assert [failure.owner_id for failure in report.failures] == ["bad"]


def test_housing_scan_reports_bad_files_and_keeps_valid_and_legacy_records(
    tmp_path, monkeypatch
):
    directory = tmp_path / "housing"
    directory.mkdir()
    monkeypatch.setattr(housing, "HOUSING_DIR", str(directory))

    (directory / "good.json").write_text(json.dumps({
        "user_id": "good", "character_name": "Good",
        "farming": {"plots": []}, "pets": [],
    }), encoding="utf-8")
    legacy_path = directory / "legacy.json"
    legacy_path.write_text(json.dumps({
        "character_name": "Legacy", "farming": {"plots": []}, "pets": [],
    }), encoding="utf-8")
    corrupt_path = directory / "corrupt.json"
    corrupt_bytes = b"{broken housing json"
    corrupt_path.write_bytes(corrupt_bytes)
    root_path = directory / "array.json"
    root_bytes = b"[]"
    root_path.write_bytes(root_bytes)
    malformed_path = directory / "malformed.json"
    malformed_path.write_text(json.dumps({
        "user_id": "malformed", "farming": {"plots": "not-a-list"},
    }), encoding="utf-8")

    report = housing.load_all_housing_report()

    assert {home["user_id"] for home in report.records} == {"good", "legacy"}
    assert {failure.owner_id for failure in report.failures} == {
        "corrupt", "array", "malformed",
    }
    assert corrupt_path.read_bytes() == corrupt_bytes
    assert root_path.read_bytes() == root_bytes
    assert "user_id" not in json.loads(legacy_path.read_text(encoding="utf-8"))


def test_housing_list_compatibility_wrapper_returns_valid_records_and_reports_failures(
    tmp_path, monkeypatch
):
    directory = tmp_path / "housing"
    directory.mkdir()
    monkeypatch.setattr(housing, "HOUSING_DIR", str(directory))
    (directory / "ok.json").write_text(
        json.dumps({"user_id": "ok", "farming": {"plots": []}, "pets": []}),
        encoding="utf-8",
    )
    (directory / "bad.json").write_text("[]", encoding="utf-8")
    reported = []
    monkeypatch.setattr(
        housing,
        "log_scan_failures",
        lambda name, report: reported.append((name, report)),
    )

    homes = housing.load_all_housing()

    assert [home["user_id"] for home in homes] == ["ok"]
    assert len(reported) == 1
    assert reported[0][0] == "housing records"
    assert reported[0][1].failures[0].owner_id == "bad"


def test_scan_failure_logger_deduplicates_unchanged_file_versions(tmp_path, monkeypatch):
    from utils.infrastructure.logging import kaia_logger

    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    messages = []
    monkeypatch.setattr(kaia_logger, "log_warning", messages.append)
    report = record_scan.ScanReport(
        records=[],
        failures=[
            record_scan.ScanFailure(
                str(path), "bad", "JSONDecodeError: invalid JSON"
            )
        ],
    )

    record_scan.log_scan_failures("test store", report)
    record_scan.log_scan_failures("test store", report)

    assert len(messages) == 1
    assert "bad.json" in messages[0]
    assert "owner=bad" in messages[0]

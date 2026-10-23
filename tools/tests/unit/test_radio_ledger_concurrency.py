"""The live radio ledger must allow dashboard snapshots during writes."""
import sqlite3

from utils.radio import ledger


def test_ledger_uses_wal_and_allows_a_write_during_a_read_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "local_ledger.sqlite3"
    monkeypatch.setattr(ledger, "telemetry_path", lambda _: str(db_path))

    writer = ledger._db()
    assert writer.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    # A dashboard opens a separate read-only connection and keeps its read
    # transaction open while the scanner records another channel.
    reader = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.2)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM channels").fetchone()
        ledger.note_probe(146_520_000, "2m", "amateur")

        rows = reader.execute("SELECT COUNT(*) FROM channels").fetchone()
        assert rows[0] == 0  # the reader retains its original WAL snapshot
        reader.commit()
        assert writer.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 1
    finally:
        reader.close()

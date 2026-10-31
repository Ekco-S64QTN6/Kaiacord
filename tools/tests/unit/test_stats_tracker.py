"""stats.json: total_users read 0 for months because its only writer,
increment_users(), had no caller. It now counts distinct message authors."""
import json
import time


def test_total_users_counts_distinct_authors_and_survives_a_restart(tmp_path, monkeypatch):
    from utils.infrastructure.monitoring import stats_tracker as st

    stats_file = tmp_path / "stats.json"
    monkeypatch.setattr(st, "telemetry_path", lambda _p: str(stats_file))

    t = st.StatsTracker()
    for uid in (111, 222, 111, None):
        t.increment_messages(uid)
    assert t.get_stats()["users"] == 2

    deadline = time.time() + 5          # saves land on a worker thread
    while time.time() < deadline:
        if stats_file.exists() and json.loads(stats_file.read_text()).get("total_messages") == 4:
            break
        time.sleep(0.05)
    saved = json.loads(stats_file.read_text())
    assert saved["total_users"] == 2 and saved["user_ids"] == ["111", "222"]

    again = st.StatsTracker()
    again.increment_messages(333)
    assert again.get_stats()["users"] == 3
